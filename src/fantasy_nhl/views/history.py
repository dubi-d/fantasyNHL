"""Player history: one player's stored NHL seasons."""
import pandas as pd

from ..analysis import (
    GAMES,
    career_average,
    is_rate,
    per_game,
    player_seasons,
    season_name,
)
from .model import INFO, TableView, View, note

COLUMN_CHOICES = {"fantasy": "Fantasy categories", "all": "All"}
CELL_CHOICES = {"total": "Season totals", "rate": "Per game"}
SKATER_COLUMNS = ["GP", "G", "A", "P", "PPP", "SHP", "STP", "SOG", "HIT",
                  "BLK", "PIM", "+/-", "TOI/GP"]
GOALIE_COLUMNS = ["GP", "GS", "W", "L", "OTL", "SA", "SV", "GA", "GAA",
                  "SV%", "SO"]


def _teams(teams: str) -> str:
    return teams.replace(",", "/")


def history_players(history: pd.DataFrame) -> dict[str, int]:
    """Unique label -> NHL player id for picking a player by name; the
    label has his position and teams of his latest season."""
    latest = (history.sort_values("season")
              .drop_duplicates("player_id", keep="last")
              .sort_values(["name", "player_id"]))
    by_label: dict[str, int] = {}
    for pid, name, position, teams in zip(
            latest["player_id"], latest["name"], latest["position"],
            latest["teams"]):
        label = f"{name} ({position}, {_teams(teams)})"
        by_label[label if label not in by_label
                 else f"{label} #{pid}"] = int(pid)
    return by_label


def _clock(seconds: float) -> str | None:
    if pd.isna(seconds):
        return None
    return "{:02d}:{:02d}".format(*divmod(round(seconds), 60))


def _shown(column: str, values: pd.Series, decimals: int) -> pd.Series:
    """A stat as displayed; ``decimals`` are those of a count (0 = whole)."""
    if column == "TOI/GP":
        return values.map(_clock).astype(object)
    if column == "SV%" or column.endswith("Pct"):
        return values.round(3)
    if is_rate(column):
        return values.round(2)
    if column == "TOI":
        values = values / 60
    return (values.round(decimals) if decimals
            else values.round(0).astype("Int64"))


def build_player_history(history: pd.DataFrame, player_id: int,
                         columns: str = "fantasy",
                         cells: str = "total") -> View:
    """
    :param history: the stored seasons, a row per player and season
    :param player_id: a player of that table (his NHL id)
    :param columns: one of COLUMN_CHOICES
    :param cells: one of CELL_CHOICES
    """
    seasons = player_seasons(history, player_id)
    latest = seasons.iloc[-1]
    goalie = latest["position"] == "G"
    rate = cells == "rate"
    shown = list(GOALIE_COLUMNS if goalie else SKATER_COLUMNS)
    if columns == "all":
        numbers = seasons.select_dtypes("number")
        # per game, the ice time is the TOI/GP column
        shown += [column for column in numbers
                  if column not in shown and numbers[column].notna().any()
                  and not (rate and column == "TOI")]
    values = (per_game(seasons) if rate else seasons).reindex(columns=shown)
    average = career_average(seasons, rate).reindex(shown).to_frame().T

    table = pd.DataFrame({
        "Season": [season_name(season) for season in seasons.index],
        "Team": [_teams(teams) for teams in seasons["teams"]]})
    footer = pd.DataFrame({"Season": ["Average"], "Team": [""]}, index=[""])
    for column in shown:
        games = column in GAMES
        table[column] = _shown(column, values[column],
                               2 if rate and not games else 0).array
        footer[column] = _shown(column, average[column],
                                2 if rate and not games else 1).array
    table.index = [""] * len(table)

    stored = sorted(history["season"].unique())
    missing = [season_name(season) for season in stored
               if season not in seasons.index]
    counts = ("per game over all his games listed (GP"
              + (" and GS" if goalie else "") + ": the mean per season)"
              if rate else "the mean of the seasons listed")
    rates = ("GAA, SV%" if goalie else "TOI/GP") + (
        ", ..." if columns == "all" else "")
    units = [text for column, text in (
        ("STP", "STP = PPP + SHP"), ("TOI/GP", "TOI/GP in minutes:seconds"),
        ("TOI", "TOI in minutes")) if column in shown]
    return View([
        TableView(f"{latest['name']} ({latest['position']}) — NHL regular "
                  f"seasons, {CELL_CHOICES[cells].lower()}", table,
                  footer=footer),
        note(f"Average: counts are {counts}; rates and ratios ({rates}) are "
             "taken over all those games together, not as the mean of the "
             "seasons." + (f" {'; '.join(units)}." if units else ""),
             level=INFO),
        note("Stored: " + (
            f"{season_name(stored[0])} to {season_name(stored[-1])}"
            if len(stored) > 1 else season_name(stored[0]))
             + (f"; no NHL games in {', '.join(missing)}" if missing else "")
             + ".", level=INFO)])
