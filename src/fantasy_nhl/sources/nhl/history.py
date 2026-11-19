"""Regular-season stats of every NHL player, stored as one CSV per season."""
import csv
import json
import re
from datetime import date, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

_API = "https://api.nhle.com/stats/rest/en"
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
    return folder / f"season_{season_id(year)}.csv"


def _get(resource: str, **params) -> dict:
    """One public request to the stats API."""
    request = Request(f"{_API}/{resource}?{urlencode(params)}",
                      headers={"User-Agent": "fantasy-nhl"})
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except (URLError, TimeoutError, ValueError) as exc:
        raise NhlStatsError(
            f"Unable to read '{resource}' from the NHL stats API.") from exc


def fetch_season_ends() -> dict[int, date]:
    """Last day of the regular season by the year a season ends in (one
    request)."""
    try:
        return {row["id"] % 10000:
                datetime.fromisoformat(row["regularSeasonEndDate"]).date()
                for row in _get("season")["data"]}
    except (KeyError, TypeError, ValueError) as exc:
        raise NhlStatsError(
            "The NHL stats API returned an unexpected season list.") from exc


def _report(report: str, year: int) -> dict[int, dict]:
    """Every row of a regular-season report, by player id."""
    answer = _get(report, limit=-1,
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


def fetch_season_stats(year: int) -> list[dict]:
    """Regular-season stats of the season ending in `year`: one row per
    player with every field the NHL reports, skaters first, a player traded
    during the season once with all his teams (three requests)."""
    summary = _report("skater/summary", year)
    realtime = _report("skater/realtime", year)
    goalies = _report("goalie/summary", year)
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


def save_season_stats(year: int, rows: list[dict],
                      folder: Path = DATA_DIR) -> Path:
    """Write a season's rows to its CSV file, replacing an existing one."""
    path = season_path(year, folder)
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


def stored_seasons(folder: Path = DATA_DIR) -> list[int]:
    """The seasons stored in `folder`, as the years they end in."""
    names = (re.fullmatch(r"season_(\d{4})(\d{4})\.csv", path.name)
             for path in folder.glob("season_*.csv"))
    return sorted(int(name[2]) for name in names
                  if name and int(name[2]) == int(name[1]) + 1)


def read_history(folder: Path = DATA_DIR) -> pd.DataFrame:
    """Every stored season as one table: a row per player and season, the
    columns of all files (COLUMNS first), blank cells missing."""
    seasons = []
    for year in stored_seasons(folder):
        path = season_path(year, folder)
        try:
            # only a blank cell is missing: "NA" could be a name
            season = pd.read_csv(path, keep_default_na=False, na_values=[""])
        except (OSError, ValueError) as exc:
            raise NhlStatsError(f"'{path}' cannot be read.") from exc
        if list(season.columns[:len(COLUMNS)]) != COLUMNS:
            raise NhlStatsError(
                f"'{path}' is not a stored season; download it again with "
                "fantasy-nhl-history --refresh.")
        seasons.append(season)
    if not seasons:
        return pd.DataFrame(columns=COLUMNS)
    return pd.concat(seasons, ignore_index=True)
