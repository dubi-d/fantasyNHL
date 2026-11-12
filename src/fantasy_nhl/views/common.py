"""Helpers shared by several views."""
from collections.abc import Iterable
from typing import TYPE_CHECKING

import pandas as pd

from ..analysis import PreviewPlayer, StatBasis, has_season_games, round_robin
from .model import BAD, EVEN, GOOD, WARN, WARNING, Note, Tone, diverging, heat, note

if TYPE_CHECKING:
    from ..sources.espn import LeagueData

RESULT_TONES = {"W": GOOD, "L": BAD, "T": EVEN}

NO_PROJECTION = "†"
NO_PROJECTION_NOTE = (f"{NO_PROJECTION} = no ESPN projection: rated on "
                      "season stats alone.")

# specific positions first; Forward/Util add no information for the label
SLOT_ABBREV = {"Center": "C", "Left Wing": "LW", "Right Wing": "RW",
               "Defense": "D", "Goalie": "G", "Forward": "F", "Util": "U"}
SLOT_ORDER = {slot: i for i, slot in enumerate(SLOT_ABBREV)}
SLOT_SHORT = {**SLOT_ABBREV, "Bench": "BN", "IR": "IR"}

# Injury statuses shared by roster and candidate tables.
INJURY_ABBREV = {"DAY_TO_DAY": "DTD", "OUT": "OUT",
                 "INJURY_RESERVE": "IR", "SUSPENSION": "SUS",
                 "ACTIVE": "", "": ""}


def position_label(eligible_slots: list[str]) -> str:
    specific = [s for s in eligible_slots if s not in ("Forward", "Util")]
    slots = sorted(specific or eligible_slots, key=SLOT_ORDER.get)
    return "/".join(SLOT_ABBREV.get(s, s) for s in slots)


def day_labels(periods: list[int],
               period_dates: dict[int, object]) -> dict[int, str]:
    return {p: (f"{period_dates[p]:%a %-d}" if p in period_dates
                else f"Day {p}") for p in periods}


def score_tone(value: float) -> Tone:
    return diverging(value, 1.5)


def points_tone(value: float) -> Tone:
    """Tone of a difference in percentage points."""
    return diverging(value, 50)


def percentile_tone(pct: float) -> Tone:
    return None if pd.isna(pct) else heat(pct / 100)


PLAYER_TONES = {
    "Score": score_tone, "Gap": points_tone, "Return": points_tone,
    "Chg": lambda v: diverging(v, 10),
    "Inj": {"DTD": WARN, "SUS": WARN, "OUT": BAD, "IR": BAD}.get}


def player_view(table: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Display copy of player/pick rows: abbreviated position/slot/injury,
    rounded numbers, rank index. Only transforms the columns present."""
    view = table.copy()
    view["Pos"] = view["Pos"].map(lambda p: SLOT_ABBREV.get(p, p or "?"))
    if "NoProj" in view:
        view["Player"] = view["Player"].where(
            ~view["NoProj"].astype(bool),
            view["Player"] + f" {NO_PROJECTION}")
    if "Slot" in view:
        view["Slot"] = view["Slot"].map(lambda s: SLOT_SHORT.get(s, s))
    if "Injury" in view:
        view["Inj"] = view["Injury"].map(
            lambda s: INJURY_ABBREV.get(s, (s or "")[:3]))
    for col in ("Own%", "Chg", "ADP"):
        if col in view:
            view[col] = view[col].round(1)
    if "Score" in view:
        view["Score"] = view["Score"].round(2)
    for col in ("Gap", "Return", "Value", "Rank", "Overall"):
        if col in view:
            view[col] = view[col].round(0).astype("Int64")
    if "Rd" in view and "Pick" in view:
        # "3.02" = round 3, 2nd pick of the round
        view["Rd.Pk"] = [f"{rd}.{pick:02d}" for rd, pick in
                         zip(view["Rd"], view["Pick"])]
    if "ValueRd" in view:
        view["Rounds"] = view["ValueRd"].round(1)
    if "NowOn" in view:
        view["NowOn"] = view["NowOn"].fillna("FA")
    view = view[columns].reset_index(drop=True)
    view.index = range(1, len(view) + 1)
    return view


def stat_basis(season_only: bool, season_fraction: float) -> StatBasis:
    return (StatBasis.season(season_fraction) if season_only
            else StatBasis.blended(season_fraction))


def basis_label(basis: StatBasis) -> str:
    if basis.season_only:
        return "this season only"
    season = round(basis.season_fraction * 100)
    return f"blended: {season}% season / {100 - season}% projection"


def with_basis(title: str, basis: StatBasis) -> str:
    return f"{title} — stats: {basis_label(basis)}"


def no_season_stats_note(basis: StatBasis,
                         players: Iterable[PreviewPlayer]) -> Note | None:
    """Warning for season-only stats when nobody has played yet."""
    if basis.season_only and not any(has_season_games(p) for p in players):
        return note("Nobody here has played this season yet, so 'This "
                    "season only' stats are empty - switch Player stats "
                    "to Blended in the main menu to use projections.",
                    level=WARNING)
    return None


def completed_matchups(data: "LeagueData") -> int:
    """Number of completed matchups; the current one counts once it has a
    decided result (season over)."""
    if any(results[data.current_week - 1] != "NA"
           for results in data.weekly_results):
        return data.current_week
    return data.current_week - 1


def ranked(table: pd.DataFrame, by: str = "Pts") -> pd.DataFrame:
    """Sort by the given points column and use the rank as index."""
    table = table.sort_values(by=[by], ascending=False)
    table.index = range(1, len(table) + 1)
    return table


def round_robin_week(data: "LeagueData", week: int) -> pd.DataFrame:
    return round_robin(data.weekly_cat_scores[:, :, week - 1],
                       data.config.categories, data.team_names)
