"""The NHL schedule mapped onto ESPN's fantasy calendar."""
import json
import re
from datetime import date, datetime, timedelta
from urllib.error import URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from espn_api.hockey import League
from espn_api.hockey.constant import PRO_TEAM_MAP

from .league import LeagueData, ScheduleData


# NHL scoring periods roll over on US/Eastern calendar days
_EASTERN = ZoneInfo("America/New_York")


def _period_dates(pro_schedule: dict, first_period: int,
                  final_period: int) -> dict[int, date]:
    """Calendar date of every scoring period, extrapolated from the earliest
    scheduled NHL game (scoring periods are consecutive Eastern-time days)."""
    dated: dict[int, date] = {}
    for games_by_period in pro_schedule.values():
        for period_str, games in games_by_period.items():
            for game in games:
                day = datetime.fromtimestamp(game["date"] / 1000,
                                             tz=_EASTERN).date()
                period = int(period_str)
                if period not in dated or day < dated[period]:
                    dated[period] = day
    if not dated:
        raise ValueError("ESPN pro schedule is empty; cannot derive weeks.")
    anchor = min(dated)
    return {p: dated[anchor] + timedelta(days=p - anchor)
            for p in range(first_period, final_period + 1)}


def _app_constants(html: str) -> dict:
    """Read ESPN's embedded JSON app state, without executing JavaScript."""
    try:
        marker = re.search(r"\b__NEXT_DATA__\s*=\s*", html)
        if marker is None:
            marker = re.search(
                r'<script\b[^>]*\bid=[\'\"]__NEXT_DATA__[\'\"][^>]*>\s*', html)
        if marker is None:
            raise ValueError("missing app state")
        state, _ = json.JSONDecoder().raw_decode(html[marker.end():])
        return state["props"]["pageProps"]["page"]["config"]["constants"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("ESPN app calendar data is missing or invalid.") from exc


def _season_periods(constants: dict, year: int,
                    period_type_id: int) -> dict[int, list[int]]:
    """Expand ESPN base periods, including extended opening/break matchups.

    League matchupPeriods contains these base period IDs, not daily scoring
    IDs. Reject missing/wrong-season data rather than guessing the calendar.
    """
    try:
        if int(constants["seasonConfig"]) != year:
            raise ValueError("wrong season")
        segment = next(s for s in constants["segments"] if s["id"] == 0)
        period_type = next(t for t in segment["periodTypes"]
                           if t["id"] == period_type_id)
        periods: dict[int, list[int]] = {}
        used: set[int] = set()
        for entry in period_type["periods"]:
            pid = int(entry["id"])
            start, end = int(entry["scoringPeriodStart"]), int(entry["scoringPeriodEnd"])
            if pid in periods or start < 1 or end < start:
                raise ValueError("invalid period range")
            days = list(range(start, end + 1))
            if used.intersection(days):
                raise ValueError("overlapping periods")
            periods[pid] = days
            used.update(days)
        if not periods:
            raise ValueError("empty periods")
        return periods
    except (KeyError, TypeError, ValueError, StopIteration) as exc:
        raise ValueError(
            f"ESPN season calendar for {year} is missing or invalid; "
            "cannot safely determine matchup dates.") from exc


def _read_calendar_resource(url: str) -> str:
    """Read only public ESPN resources; never send league cookies."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {
            "fantasy.espn.com", "cdn1.espn.net"}:
        raise ValueError("Unexpected ESPN calendar resource URL.")
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")
    except (URLError, TimeoutError, UnicodeError) as exc:
        raise ValueError(
            "Unable to load ESPN season calendar; "
            "cannot safely determine matchup dates.") from exc


def _archived_calendar(html: str, year: int) -> dict:
    """Follow the app's season-specific static chunk for archived calendars.

    ESPN's initial page ignores seasonId and always embeds the current season.
    Its client loads older constants from a versioned chunk. Discover that
    resource from the current bundle instead of pinning deployment hashes.
    Only the segment data literal is parsed; no downloaded code is executed.
    """
    try:
        main = re.search(
            r'<script\b[^>]*\bsrc=[\'\"]([^\'\"]+/_next/static/commons/'
            r'main-[^\'\"]+\.js)[\'\"]', html)
        if main is None:
            raise ValueError("missing app bundle")
        main_url = urljoin("https://fantasy.espn.com/", main.group(1))
        bundle = _read_calendar_resource(main_url)
        chunk = re.search(
            rf'\b(\d+):"(chunks/modules_api_lm_seasons_fhl_{year}_[a-f0-9]+)"',
            bundle)
        if chunk is None:
            raise ValueError("missing season chunk")
        chunk_id, name = chunk.groups()
        digest = re.search(rf'\b{chunk_id}:"([a-f0-9]{{20}})"', bundle)
        if digest is None:
            raise ValueError("missing chunk hash")
        chunk_url = urljoin(main_url, f"../../webpack/{name}-{digest.group(1)}.js")
        source = _read_calendar_resource(chunk_url)
        season = re.search(r"\bseasonConfig:(\d+)\b", source)
        literal = re.search(r"\.exports=(?=\[\{id:0,periodTypes:)", source)
        if season is None or int(season.group(1)) != year or literal is None:
            raise ValueError("missing or wrong-season segment data")
        # Segment literals contain arrays, numbers, booleans and bare keys.
        quoted = re.sub(r'([{,])([A-Za-z_$][\w$]*):', r'\1"\2":',
                        source[literal.end():])
        segments, _ = json.JSONDecoder().raw_decode(quoted)
        return {"seasonConfig": year, "segments": segments}
    except (TypeError, ValueError) as exc:
        raise ValueError(f"ESPN archived calendar for {year} is unavailable "
                         "or invalid; cannot safely determine matchup dates.") from exc


def _fetch_season_periods(year: int, period_type_id: int) -> dict[int, list[int]]:
    """Read current or archived app calendar constants without league cookies."""
    url = f"https://fantasy.espn.com/hockey/league/schedule?seasonId={year}"
    html = _read_calendar_resource(url)
    constants = _app_constants(html)
    if int(constants.get("seasonConfig", 0)) != year:
        constants = _archived_calendar(html, year)
    return _season_periods(constants, year, period_type_id)


def _week_scoring_periods(league: League, period_dates: dict[int, date],
                          season_periods: dict[int, list[int]],
                          ) -> dict[int, list[int]]:
    """Expand league matchup IDs through ESPN's authoritative base periods.

    League-defined multi-period matchups work without special playoff logic.
    Clip to the league's scoring dates; never add phantom NHL-only matchups.
    """
    mapping: dict[int, list[int]] = {}
    used: set[int] = set()
    try:
        for week, period_ids in sorted(league.settings.matchup_periods.items(),
                                       key=lambda item: int(item[0])):
            days = [p for pid in period_ids for p in season_periods[int(pid)]
                    if p in period_dates]
            if len(set(days)) != len(days) or used.intersection(days):
                raise ValueError("overlapping matchup periods")
            if days:
                mapping[int(week)] = sorted(days)
                used.update(days)
        if not mapping:
            raise ValueError("empty matchup calendar")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("ESPN matchup calendar does not match league settings; "
                         "cannot safely determine matchup dates.") from exc
    return mapping


def _playing_by_period(pro_schedule: dict) -> dict[int, set[str]]:
    """NHL team names with a game per scoring period."""
    playing: dict[int, set[str]] = {}
    for team_id, games_by_period in pro_schedule.items():
        name = PRO_TEAM_MAP.get(team_id)
        if name is None:
            continue
        for period_str, games in games_by_period.items():
            if games:
                playing.setdefault(int(period_str), set()).add(name)
    return playing


def _game_starts(pro_schedule: dict) -> dict[int, dict[str, datetime]]:
    """Start time of each NHL team's game per scoring period."""
    starts: dict[int, dict[str, datetime]] = {}
    for team_id, games_by_period in pro_schedule.items():
        name = PRO_TEAM_MAP.get(team_id)
        if name is None:
            continue
        for period_str, games in games_by_period.items():
            if games:
                start = min(datetime.fromtimestamp(g["date"] / 1000, tz=_EASTERN)
                            for g in games)
                starts.setdefault(int(period_str), {})[name] = start
    return starts


def fetch_schedule_data(data: LeagueData) -> ScheduleData:
    """Cached NHL schedule and exact fantasy calendar (pro-schedule plus
    public ESPN app-calendar requests, including archive chunks if needed)."""
    if data.schedule is None:
        league = data.espn_league
        if league is None:
            raise ValueError("LeagueData has no live ESPN session.")
        pro_schedule = league._get_all_pro_schedule()
        period_dates = _period_dates(pro_schedule, league.firstScoringPeriod,
                                     league.finalScoringPeriod)
        settings = league.settings._raw_schedule_settings
        season_periods = _fetch_season_periods(
            data.config.year, int(settings["periodTypeId"]))
        week_periods = _week_scoring_periods(league, period_dates, season_periods)
        data.schedule = ScheduleData(
            playing_by_period=_playing_by_period(pro_schedule),
            period_dates=period_dates,
            week_periods=week_periods,
            game_starts=_game_starts(pro_schedule),
        )
    return data.schedule


def fetch_week_dates(data: LeagueData) -> dict[int, tuple[date, date]]:
    """First and last calendar day of every matchup week (cached)."""
    if data.week_dates is None:
        schedule = fetch_schedule_data(data)
        data.week_dates = {w: (schedule.period_dates[min(ps)],
                               schedule.period_dates[max(ps)])
                           for w, ps in schedule.week_periods.items() if ps}
    return data.week_dates
