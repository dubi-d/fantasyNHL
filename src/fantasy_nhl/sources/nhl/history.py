"""Regular-season stats of every NHL player, stored as one CSV per season."""
import csv
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

_API = "https://api.nhle.com/stats/rest/en"
_TIMEOUT = 30  # seconds per request
_QUICK = 10  # while a page waits for the answer
# relative to the working directory, like config.yaml
DATA_DIR = Path("data") / "nhl"

# CSV column -> the NHL field it renames; a row needs those of its group
_SKATER = {"GP": "gamesPlayed", "G": "goals", "A": "assists",
           "PPP": "ppPoints", "SHP": "shPoints", "SOG": "shots",
           "HIT": "hits", "BLK": "blockedShots"}
_GOALIE = {"GP": "gamesPlayed", "GS": "gamesStarted", "W": "wins",
           "L": "losses", "OTL": "otLosses", "SA": "shotsAgainst",
           "SV": "saves", "GA": "goalsAgainst",
           "GAA": "goalsAgainstAverage", "SV%": "savePct", "SO": "shutouts"}
_COLUMN_OF = {field: column
              for column, field in {**_SKATER, **_GOALIE}.items()}
_IDENTITY = {"seasonId", "playerId", "skaterFullName", "goalieFullName",
             "positionCode", "teamAbbrevs"}
# the leading columns of every file; the NHL's other fields follow by name
COLUMNS = ["season", "player_id", "name", "position", "teams",
           *dict.fromkeys([*_SKATER, *_GOALIE])]


class NhlStatsError(Exception):
    """The NHL stats API could not be read or answered unexpectedly."""


def season_id(year: int) -> int:
    """The NHL's id of the season ending in `year` (2026 -> 20252026)."""
    return (year - 1) * 10000 + year


def season_label(year: int) -> str:
    """The season ending in `year` as it is written (2026 -> '2025-26')."""
    return f"{year - 1}-{year % 100:02d}"


def season_path(year: int, folder: Path = DATA_DIR) -> Path:
    """The file of a finished season."""
    return folder / f"season_{season_id(year)}.csv"


def current_path(year: int, folder: Path = DATA_DIR) -> Path:
    """The file of a season while it is played."""
    return folder / f"current_{season_id(year)}.csv"


def _get(resource: str, timeout: float = _TIMEOUT, **params) -> dict:
    """One public request to the stats API."""
    request = Request(f"{_API}/{resource}?{urlencode(params)}",
                      headers={"User-Agent": "fantasy-nhl"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except (URLError, TimeoutError, ValueError) as exc:
        raise NhlStatsError(
            f"Unable to read '{resource}' from the NHL stats API.") from exc


def _season_dates(field: str, timeout: float = _TIMEOUT) -> dict[int, date]:
    """A date of every season by the year it ends in (one request)."""
    try:
        return {row["id"] % 10000: datetime.fromisoformat(row[field]).date()
                for row in _get("season", timeout)["data"]}
    except (KeyError, TypeError, ValueError) as exc:
        raise NhlStatsError(
            "The NHL stats API returned an unexpected season list.") from exc


def fetch_season_ends() -> dict[int, date]:
    """Last day of the regular season by the year a season ends in (one
    request)."""
    return _season_dates("regularSeasonEndDate")


def fetch_current_season(today: date | None = None,
                         timeout: float = _TIMEOUT) -> int:
    """The newest season that has started, as the year it ends in (one
    request). It stays the current one until the next season starts."""
    today = today or date.today()
    starts = _season_dates("startDate", timeout)
    started = [year for year, start in starts.items() if start <= today]
    if not started:
        raise NhlStatsError("The NHL stats API lists no season that has "
                            "started.")
    return max(started)


def _report(report: str, year: int, timeout: float) -> dict[int, dict]:
    """Every row of a regular-season report, by player id."""
    answer = _get(report, timeout, limit=-1,
                  cayenneExp=f"seasonId={season_id(year)} and gameTypeId=2")
    try:
        rows = {row["playerId"]: row for row in answer["data"]}
        complete = len(rows) == len(answer["data"]) == answer["total"]
    except (KeyError, TypeError) as exc:
        raise NhlStatsError(
            f"The NHL stats API returned an unexpected '{report}' report."
        ) from exc
    if not complete:
        raise NhlStatsError(
            f"The NHL stats API returned an incomplete '{report}' report "
            f"for {season_label(year)}.")
    return rows


def _row(year: int, raw: dict, name_field: str,
         required: dict[str, str]) -> dict:
    """A player's row: his identity, then every other field of `raw`, under
    its column of COLUMNS if it has one and under its NHL name if not."""
    absent = {name_field, "positionCode", "teamAbbrevs",
              *required.values()} - raw.keys()
    if absent:
        raise NhlStatsError("The NHL stats API no longer reports "
                            f"{', '.join(sorted(absent))}.")
    row = {"season": season_id(year), "player_id": raw["playerId"],
           "name": raw[name_field], "position": raw["positionCode"],
           "teams": raw["teamAbbrevs"]}
    row.update((_COLUMN_OF.get(field, field), value)
               for field, value in raw.items() if field not in _IDENTITY)
    return row


def fetch_season_stats(year: int, timeout: float = _TIMEOUT) -> list[dict]:
    """Regular-season stats of the season ending in `year`: one row per
    player with every field the NHL reports, skaters first, a player traded
    during the season once with all his teams (three requests)."""
    summary = _report("skater/summary", year, timeout)
    realtime = _report("skater/realtime", year, timeout)
    goalies = _report("goalie/summary", year, timeout)
    if summary.keys() != realtime.keys():
        raise NhlStatsError(
            f"The NHL's skater reports for {season_label(year)} list "
            "different players.")
    # a field both skater reports carry is taken from the summary
    skaters = [_row(year, {**realtime[player_id], **raw}, "skaterFullName",
                    _SKATER)
               for player_id, raw in sorted(summary.items())]
    return skaters + [
        _row(year, {**raw, "positionCode": "G"}, "goalieFullName", _GOALIE)
        for _, raw in sorted(goalies.items())]


def _write(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    others = sorted({column for row in rows for column in row} - set(COLUMNS))
    # a half-written file would later be taken for a stored season
    partial = path.with_suffix(".part")
    with partial.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS + others)
        writer.writeheader()
        writer.writerows(rows)
    partial.replace(path)
    return path


def save_season_stats(year: int, rows: list[dict],
                      folder: Path = DATA_DIR) -> Path:
    """Write a finished season's rows to its CSV file, replacing an
    existing one; its file from while it was played is removed."""
    path = _write(season_path(year, folder), rows)
    current_path(year, folder).unlink(missing_ok=True)
    return path


def refresh_current_season(folder: Path = DATA_DIR) -> Path | None:
    """Download the current season and store it as its file of `folder`,
    replacing an earlier download (four requests). Nothing is downloaded,
    and None returned, if it is stored as a finished season."""
    year = fetch_current_season(timeout=_QUICK)
    if year in stored_seasons(folder):
        return None
    return _write(current_path(year, folder),
                  fetch_season_stats(year, timeout=_QUICK))


def _seasons(folder: Path, kind: str) -> list[int]:
    names = (re.fullmatch(kind + r"_(\d{4})(\d{4})\.csv", path.name)
             for path in folder.glob(f"{kind}_*.csv"))
    return sorted(int(name[2]) for name in names
                  if name and int(name[2]) == int(name[1]) + 1)


def stored_seasons(folder: Path = DATA_DIR) -> list[int]:
    """The finished seasons stored in `folder`, as the years they end in."""
    return _seasons(folder, "season")


def current_file(folder: Path = DATA_DIR) -> Path | None:
    """The stored current season of `folder`: the newest season with a
    file from while it is played, unless it is stored as finished."""
    played = _seasons(folder, "current")
    if not played or played[-1] in stored_seasons(folder):
        return None
    return current_path(played[-1], folder)


def _read(path: Path, remedy: str) -> pd.DataFrame:
    try:
        # only a blank cell is missing: "NA" could be a name
        season = pd.read_csv(path, keep_default_na=False, na_values=[""])
    except (OSError, ValueError) as exc:
        raise NhlStatsError(f"'{path}' cannot be read.") from exc
    if list(season.columns[:len(COLUMNS)]) != COLUMNS:
        raise NhlStatsError(f"'{path}' is not a stored season; {remedy}.")
    return season


def read_history(folder: Path = DATA_DIR) -> pd.DataFrame:
    """Every stored finished season as one table: a row per player and
    season, the columns of all files (COLUMNS first), blank cells
    missing."""
    seasons = [_read(season_path(year, folder), "download it again with "
                     "fantasy-nhl-history --refresh")
               for year in stored_seasons(folder)]
    if not seasons:
        return pd.DataFrame(columns=COLUMNS)
    return pd.concat(seasons, ignore_index=True)


@dataclass(frozen=True)
class CurrentSeason:
    """The season being played, as it was last downloaded."""
    season: int  # the NHL's id
    stats: pd.DataFrame  # a row per player, as in read_history
    loaded: datetime  # when it was downloaded


def read_current_season(path: Path) -> CurrentSeason:
    """The current season stored in `path` (see current_file); it was
    downloaded when the file was last written."""
    stats = _read(path, "refresh the current season to replace it")
    years = re.fullmatch(r"current_(\d{8})\.csv", path.name)
    return CurrentSeason(
        int(years[1]), stats,
        datetime.fromtimestamp(path.stat().st_mtime).astimezone())
