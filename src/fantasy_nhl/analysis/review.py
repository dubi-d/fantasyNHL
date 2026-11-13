"""Roster review tables: origins, draft return, acquisitions, gaps."""
from collections.abc import Iterable

import pandas as pd

from .models import (
    _IR_SLOT,
    ACQUIRED_ADD,
    ACQUIRED_DRAFT,
    ACQUIRED_TRADE,
    DraftPick,
    RosterPlayer,
    TransactionCounts,
    position_group,
)
from .ranking import percentile_ranks
from .rates import _stat_games


def _player_row(player: RosterPlayer, values: pd.DataFrame,
                team_names: list[str]) -> dict:
    value = (values.loc[player.player_id]
             if player.player_id in values.index else None)
    return {
        "Player": player.name,
        "Pos": player.position,
        "TeamRow": player.team_row,
        "Team": ("FA" if player.team_row is None
                 else team_names[player.team_row]),
        "Slot": player.lineup_slot,
        "Acq": player.acquisition,
        "GP": int(_stat_games(player.season_stats)),
        "Own%": player.pct_owned,
        "Chg": player.pct_change,
        "Score": None if value is None else value["Score"],
        "Gap": None if value is None else value["Gap"],
        "Injury": player.injury,
        "NoProj": False if value is None else bool(value["NoProj"]),
    }


_PLAYER_COLUMNS = ["Player", "Pos", "TeamRow", "Team", "Slot", "Acq", "GP",
                   "Own%", "Chg", "Score", "Gap", "Injury", "NoProj"]


def player_table(players: Iterable[RosterPlayer], values: pd.DataFrame,
                 team_names: list[str]) -> pd.DataFrame:
    """One row per player with ownership, origin and value columns."""
    rows = [_player_row(p, values, team_names) for p in players]
    return pd.DataFrame(rows, columns=_PLAYER_COLUMNS).astype(
        {"Own%": float, "Chg": float, "Score": float, "Gap": float,
         "NoProj": bool})


def roster_origins(rosters: list[list[RosterPlayer]], values: pd.DataFrame,
                   team_names: list[str],
                   counters: list[TransactionCounts]) -> pd.DataFrame:
    """
    Per team (index = team row): roster size and how it was assembled
    (drafted, added, traded-in, on IR), the average roster% and Score of
    its players, and the season's add/drop/trade counters.
    """
    rows = []
    for row, players in enumerate(rosters):
        table = player_table(players, values, team_names)
        rows.append({
            "Player": team_names[row],
            "Size": len(players),
            "Drafted": int((table["Acq"] == ACQUIRED_DRAFT).sum()),
            "Added": int((table["Acq"] == ACQUIRED_ADD).sum()),
            "Traded": int((table["Acq"] == ACQUIRED_TRADE).sum()),
            "IR": sum(p.lineup_slot == _IR_SLOT for p in players),
            "Avg Own%": table["Own%"].mean(),
            "Avg Score": table["Score"].mean(),
            "Adds": counters[row].adds,
            "Drops": counters[row].drops,
            "Trades": counters[row].trades,
        })
    return pd.DataFrame(rows, index=pd.Index(range(len(rosters)),
                                            name="TeamRow"))


def draft_return(picks: list[DraftPick], values: pd.DataFrame,
                 team_names: list[str],
                 players: dict[int, RosterPlayer] | None = None) -> pd.DataFrame:
    """
    How every draft pick has panned out: Return = the player's Score
    percentile (within his position group in the pool) minus the percentile
    of his draft slot among the picks (pick 1 = 100), in percentage points.
    Positive: producing more than the slot he cost; negative: a bust. A
    pick who is in the pool but has no Score (too few games) counts as the
    0th percentile - he delivered nothing for the slot. Roster% is carried
    along for information only - it reflects ESPN's default settings, not
    this league's categories.

    :param players: current player info by id, for the GP column
    """
    players = players or {}
    slot_pct = percentile_ranks(-p.overall for p in picks)
    rows = []
    for pick, slot in zip(picks, slot_pct):
        value = (values.loc[pick.player_id]
                 if pick.player_id in values.index else None)
        score_pct = None if value is None else value["ScorePct"]
        if value is not None and pd.isna(score_pct):
            score_pct = 0.0
        player = players.get(pick.player_id)
        rows.append({
            "Player": pick.name,
            "Pos": pick.position,
            "TeamRow": pick.team_row,
            "Team": team_names[pick.team_row],
            "Rd": pick.round,
            "Pick": pick.pick_in_round,
            "Overall": pick.overall,
            "GP": int(_stat_games(player.season_stats)) if player else None,
            "Own%": pick.pct_owned,
            "Score": None if value is None else value["Score"],
            "Return": (None if score_pct is None or pd.isna(score_pct)
                       else float(score_pct) - slot),
            "NowOn": (None if pick.rostered_by is None
                      else team_names[pick.rostered_by]),
            "NoProj": False if value is None else bool(value["NoProj"]),
        })
    return pd.DataFrame(rows, columns=[
        "Player", "Pos", "TeamRow", "Team", "Rd", "Pick", "Overall", "GP",
        "Own%", "Score", "Return", "NowOn", "NoProj"]).astype(
            {"GP": "Int64", "Own%": float, "Score": float, "Return": float,
             "NoProj": bool})


def acquisition_summary(rosters: list[list[RosterPlayer]],
                        values: pd.DataFrame, team_names: list[str],
                        acquisition: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Players each team acquired a given way (ADD = free-agent/waiver pickups,
    TRADE = traded in), ranked by Score, plus a per-team summary (index =
    team row) with the count, average roster%/Score and the best player.
    """
    acquired = [p for players in rosters for p in players
                if p.acquisition == acquisition]
    table = player_table(acquired, values, team_names)
    table = table.sort_values("Score", ascending=False, na_position="last",
                              kind="stable").reset_index(drop=True)
    rows = []
    for row, name in enumerate(team_names):
        own = table[table["TeamRow"] == row]
        best = own.iloc[0]["Player"] if len(own) and not pd.isna(
            own.iloc[0]["Score"]) else None
        rows.append({
            "Player": name,
            "Count": len(own),
            "Avg Own%": own["Own%"].mean() if len(own) else None,
            "Avg Score": own["Score"].mean() if len(own) else None,
            "Best": best,
        })
    summary = pd.DataFrame(rows, index=pd.Index(range(len(team_names)),
                                                name="TeamRow"))
    return summary.astype({"Avg Own%": float, "Avg Score": float}), table


def market_gaps(roster: list[RosterPlayer], free_agents: list[RosterPlayer],
                values: pd.DataFrame, team_names: list[str],
                n: int, n_goalies: int) -> tuple[pd.DataFrame, pd.DataFrame,
                                                 pd.DataFrame]:
    """
    Drop candidates (the roster's n lowest-scoring players, weakest first;
    players without a Score come first) and free-agent targets - the n
    highest-scoring skaters and the n_goalies highest-scoring goalies,
    separately since Scores compare within a position group - each with
    the crowd-vs-stats Gap.
    """
    drops = player_table(roster, values, team_names)
    drops = drops.sort_values("Score", na_position="first",
                              kind="stable").head(n).reset_index(drop=True)
    skaters = [p for p in free_agents if position_group(p) != "G"]
    goalies = [p for p in free_agents if position_group(p) == "G"]

    def top(players: list[RosterPlayer], limit: int) -> pd.DataFrame:
        table = player_table(players, values, team_names)
        return table.sort_values("Score", ascending=False, na_position="last",
                                 kind="stable").head(limit).reset_index(drop=True)
    return drops, top(skaters, n), top(goalies, n_goalies)
