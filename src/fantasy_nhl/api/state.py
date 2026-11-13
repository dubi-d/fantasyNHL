"""Server-side league state: every configured league, loaded on first use
and again once the load is old, with a short-lived cache of what else was
fetched from ESPN."""
import logging
import re
import threading
import time
import traceback
from collections.abc import Callable
from datetime import datetime
from typing import Any

from ..config import LeagueConfig
from ..sources.espn import LeagueData, fetch_league_data

CACHE_SECONDS = 300  # a fetch within a session
SESSION_SECONDS = 900  # the league load itself

log = logging.getLogger(__name__)


class UpstreamError(Exception):
    """ESPN could not be reached or answered unexpectedly."""


def _upstream(league_id: str, fetch: Callable[[], Any]) -> Any:
    try:
        return fetch()
    except Exception as error:  # espn_api raises a variety of types
        # where it failed, without the message: espn_api's carry the cookies
        log.error("ESPN request for league %s failed: %s\n%s", league_id,
                  type(error).__name__,
                  "".join(traceback.format_tb(error.__traceback__)))
        raise UpstreamError(type(error).__name__) from None


class LeagueSession:
    """One load of a league and what was fetched and derived for it. A
    reload starts a new session, so nothing of an old load reaches it."""

    def __init__(self, league_id: str, config: LeagueConfig,
                 data: LeagueData) -> None:
        self.id = league_id
        self.config = config
        self.data = data
        self.loaded_at = datetime.now().astimezone()
        self._born = time.monotonic()
        # espn_api's client and the caches on LeagueData are not thread-safe
        self._lock = threading.RLock()
        self._cache: dict[tuple, tuple[float, Any]] = {}
        self._derived: dict[tuple, tuple[Any, Any]] = {}

    @property
    def expired(self) -> bool:
        return time.monotonic() - self._born >= SESSION_SECONDS

    def cached(self, key: tuple, compute: Callable[[], Any]) -> Any:
        """The value of ``compute``, reused for CACHE_SECONDS per key."""
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
                return hit[1]
            value = compute()
            now = time.monotonic()
            self._cache = {k: entry for k, entry in self._cache.items()
                           if now - entry[0] < CACHE_SECONDS}
            self._cache[key] = (now, value)
            return value

    def fetch(self, key: tuple, fetch: Callable[[], Any]) -> Any:
        """A cached ESPN fetch; failures become UpstreamError."""
        return self.cached(key, lambda: _upstream(self.id, fetch))

    def derived(self, key: tuple, source: Any,
                compute: Callable[[], Any]) -> Any:
        """A value computed from a fetched ``source``, kept until that
        source is fetched anew."""
        with self._lock:
            hit = self._derived.get(key)
            if hit is None or hit[0] is not source:
                hit = (source, compute())
                self._derived[key] = hit
            return hit[1]


class LeagueEntry:
    """A configured league and its current session."""

    def __init__(self, league_id: str, config: LeagueConfig) -> None:
        self.id = league_id
        self.config = config
        self._lock = threading.Lock()
        self._session: LeagueSession | None = None

    def session(self) -> LeagueSession:
        """The current session, loading the league if there is none or it
        has grown old."""
        with self._lock:
            if self._session is None or self._session.expired:
                self._session = LeagueSession(self.id, self.config, _upstream(
                    self.id, lambda: fetch_league_data(self.config)))
            return self._session

    def reload(self) -> None:
        """Forget the session, so the next request reads ESPN anew."""
        with self._lock:
            self._session = None


class LeagueStore:
    def __init__(self, configs: list[LeagueConfig]) -> None:
        self.leagues: dict[str, LeagueEntry] = {}
        for config in configs:
            base = re.sub(r"[^a-z0-9]+", "-", config.name.lower()).strip("-")
            league_id = base or "league"
            if league_id in self.leagues:
                league_id = f"{league_id}-{config.year}"
            if league_id in self.leagues:
                league_id = f"{league_id}-{len(self.leagues)}"
            self.leagues[league_id] = LeagueEntry(league_id, config)
