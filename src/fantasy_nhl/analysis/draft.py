"""Draft picks against ADP and the rosters as drafted."""
import pandas as pd

from .models import ACQUIRED_DRAFT, DraftPick, RosterPlayer


_DEFENSE_POSITION = "Defense"
_GOALIE_POSITION = "Goalie"


def draft_pick_table(picks: list[DraftPick], team_names: list[str],
                     n_teams: int) -> pd.DataFrame:
    """
    One row per draft pick in draft order. Value = overall pick − ADP, so a
    positive value means the player went later than ESPN's average draft
    position (a steal), negative means a reach. Players without an ESPN ADP
    are floored at one pick after the last one (flagged in 'ADP?').

    :param n_teams: picks per round, to express Value in rounds as well
    """
    total = max((p.overall for p in picks), default=0)
    rows = []
    for p in picks:
        missing = p.adp is None or p.adp <= 0
        adp = float(total + 1) if missing else float(p.adp)
        rows.append({
            "TeamRow": p.team_row,
            "Team": team_names[p.team_row],
            "Rd": p.round,
            "Pick": p.pick_in_round,
            "Overall": p.overall,
            "Player": p.name,
            "Pos": p.position,
            "ADP": adp,
            "ADP?": missing,
            "Value": p.overall - adp,
            "ValueRd": (p.overall - adp) / n_teams,
            "Own%": p.pct_owned,
            "Chg": p.pct_change,
            "Rank": p.espn_rank,
            "NowOn": (None if p.rostered_by is None
                      else team_names[p.rostered_by]),
        })
    return pd.DataFrame(rows, columns=[
        "TeamRow", "Team", "Rd", "Pick", "Overall", "Player", "Pos", "ADP",
        "ADP?", "Value", "ValueRd", "Own%", "Chg", "Rank", "NowOn"])


def draft_team_summary(table: pd.DataFrame) -> pd.DataFrame:
    """
    Per drafting team (index = team row): average and total pick Value, the
    best steal and biggest reach, goalie/defense counts, the round of the
    first goalie and how many own picks are still on the roster.
    """
    rows = []
    index = []
    for row, group in table.groupby("TeamRow", sort=True):
        index.append(row)
        best = group.loc[group["Value"].idxmax()]
        worst = group.loc[group["Value"].idxmin()]
        goalies = group[group["Pos"] == _GOALIE_POSITION]
        rows.append({
            "Player": group["Team"].iloc[0],
            "Avg value": group["Value"].mean(),
            "Total": group["Value"].sum(),
            "Best steal": f"{best['Player']} ({best['Value']:+.0f})",
            "Biggest reach": f"{worst['Player']} ({worst['Value']:+.0f})",
            "G": len(goalies),
            "1st G": int(goalies["Rd"].min()) if len(goalies) else None,
            "D": int((group["Pos"] == _DEFENSE_POSITION).sum()),
            "Kept": int((group["NowOn"] == group["Team"]).sum()),
            "Picks": len(group),
        })
    return pd.DataFrame(rows, index=pd.Index(index, name="TeamRow"))


def draft_value_grid(table: pd.DataFrame) -> pd.DataFrame:
    """Pick Value per team (rows, team-row order) and round (columns R1..Rn);
    several picks in one round add up."""
    grid = table.pivot_table(index="TeamRow", columns="Rd", values="Value",
                             aggfunc="sum")
    names = table.drop_duplicates("TeamRow").set_index("TeamRow")["Team"]
    grid.index = pd.Index([names[row] for row in grid.index], name="Team")
    grid.columns = [f"R{r}" for r in grid.columns]
    return grid


def draft_extremes(table: pd.DataFrame,
                   n: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """League-wide top-n steals (largest Value) and reaches (smallest);
    ties at the cutoff keep draft order."""
    return (table.nlargest(n, "Value", keep="first"),
            table.nsmallest(n, "Value", keep="first"))


def drafted_rosters(picks: list[DraftPick],
                    n_teams: int) -> list[list[RosterPlayer]]:
    """Draft-day rosters (projections only, drafted by the drafting team)
    by team row."""
    rosters: list[list[RosterPlayer]] = [[] for _ in range(n_teams)]
    for p in picks:
        rosters[p.team_row].append(RosterPlayer(
            name=p.name, pro_team="", eligible_slots=list(p.eligible_slots),
            projected_stats=dict(p.projected_stats), player_id=p.player_id,
            position=p.position, acquisition=ACQUIRED_DRAFT,
            team_row=p.team_row, pct_owned=p.pct_owned,
            pct_change=p.pct_change, espn_rank=p.espn_rank, adp=p.adp))
    return rosters
