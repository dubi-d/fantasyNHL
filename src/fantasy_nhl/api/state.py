"""Server-side league sessions: every configured league, loaded on first
use, with a short-lived cache of what was fetched from ESPN."""
import logging
import re
import threading
import time
from collections.abc import Callable
from typing import Any

from ..config import LeagueConfig
from ..sources.espn import LeagueData, fetch_league_data

CACHE_SECONDS = 300

log = logging.getLogger(__name__)


class UpstreamError(Exception):
    """ESPN could not be reached or answered unexpectedly."""


class LeagueSession:
    def __init__(self, league_id: str, config: LeagueConfig) -> None:
        self.id = league_id
        self.config = config
        # espn_api's client and the caches on LeagueData are not thread-safe
        self._lock = threading.RLock()
        self._data: LeagueData | None = None
        self._cache: dict[tuple, tuple[float, Any]] = {}

    @property
    def data(self) -> LeagueData:
        with self._lock:
            if self._data is None:
                self._data = self._upstream(
                    lambda: fetch_league_data(self.config))
            return self._data

    def cached(self, key: tuple, compute: Callable[[], Any]) -> Any:
        """The value of ``compute``, reused for CACHE_SECONDS per key."""
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
                return hit[1]
            value = compute()
            self._cache[key] = (time.monotonic(), value)
            return value

    def fetch(self, key: tuple, fetch: Callable[[], Any]) -> Any:
        """A cached ESPN fetch; failures become UpstreamError."""
        return self.cached(key, lambda: self._upstream(fetch))

    def reload(self) -> None:
        """Forget everything fetched, so the next request reads ESPN anew."""
        with self._lock:
            self._data = None
            self._cache.clear()

    def _upstream(self, fetch: Callable[[], Any]) -> Any:
        try:
            return fetch()
        except Exception as error:  # espn_api raises a variety of types
            log.exception("ESPN request for league %s failed", self.id)
            raise UpstreamError(type(error).__name__) from error


class LeagueStore:
    def __init__(self, configs: list[LeagueConfig]) -> None:
        self.sessions: dict[str, LeagueSession] = {}
        for config in configs:
            base = re.sub(r"[^a-z0-9]+", "-", config.name.lower()).strip("-")
            league_id = base or "league"
            if league_id in self.sessions:
                league_id = f"{league_id}-{config.year}"
            if league_id in self.sessions:
                league_id = f"{league_id}-{len(self.sessions)}"
            self.sessions[league_id] = LeagueSession(league_id, config)
