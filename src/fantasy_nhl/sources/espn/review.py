"""Rosters, free agents and the draft with ESPN's ownership info."""
from dataclasses import dataclass

from espn_api.hockey import League

from ...analysis import DraftPick, RosterPlayer, TransactionCounts
from .league import LeagueData
from .players import (
    _blend_weight,
    _entry_player,
    _fetch_free_agent_entries,
    _fetch_player_info,
    _fetch_roster_settings,
    _roster_player,
)


def _build_picks(league: League, info: dict[int, dict],
                 year: int) -> list[DraftPick]:
    """DraftPicks from the league session's draft and raw player entries."""
    n_teams = len(league.teams)
    row_by_team_id = {team.team_id: row for row, team in enumerate(league.teams)}
    rostered_by = {player.playerId: row
                   for row, team in enumerate(league.teams)
                   for player in team.roster}
    picks = []
    for pick in league.draft:
        entry = info.get(pick.playerId)
        player = _entry_player(entry, year) if entry else None
        picks.append(DraftPick(
            team_row=row_by_team_id[pick.team.team_id],
            round=pick.round_num,
            pick_in_round=pick.round_pick,
            overall=(pick.round_num - 1) * n_teams + pick.round_pick,
            player_id=pick.playerId,
            name=player.name if player else pick.playerName,
            position=player.position if player else "",
            eligible_slots=player.eligible_slots if player else [],
            adp=player.adp if player else None,
            pct_owned=player.pct_owned if player else None,
            pct_change=player.pct_change if player else None,
            espn_rank=player.espn_rank if player else None,
            projected_stats=player.projected_stats if player else {},
            rostered_by=rostered_by.get(pick.playerId),
        ))
    return picks


@dataclass
class RosterReviewData:
    """Current rosters, free agents and the draft, all with ESPN's ownership
    info (team order matches LeagueData)."""
    rosters: list[list[RosterPlayer]]  # by team row, all slots incl. Bench/IR
    free_agents: list[RosterPlayer]  # most-owned first
    picks: list[DraftPick]  # empty if not drafted
    drafted_players: dict[int, RosterPlayer]  # player id -> current info
    counters: list[TransactionCounts]  # by team row
    blend_weight: float  # weight of current-season rates vs projections
    slot_counts: dict[str, int]
    n_teams: int


def _fetch_transaction_counts(league: League) -> list[TransactionCounts]:
    raw = league.espn_request.league_get(params={"view": "mTeam"})
    by_id = {}
    for team in raw.get("teams", []):
        counter = team.get("transactionCounter") or {}
        by_id[team["id"]] = TransactionCounts(
            adds=int(counter.get("acquisitions", 0) or 0),
            drops=int(counter.get("drops", 0) or 0),
            trades=int(counter.get("trades", 0) or 0))
    return [by_id.get(team.team_id, TransactionCounts()) for team in league.teams]


def fetch_roster_review(data: LeagueData, fa_size: int = 200) -> RosterReviewData:
    """Everything for the in-season roster review: rosters (all slots) and
    the draft joined with ESPN ownership, the most-owned free agents and
    the transaction counters (settings, team and ~3 player-info requests)."""
    league = data.espn_league
    if league is None:
        raise ValueError("LeagueData has no live ESPN session.")
    year = data.config.year
    slot_counts, _ = _fetch_roster_settings(league)

    rostered_ids = [p.playerId for team in league.teams for p in team.roster]
    drafted_ids = [p.playerId for p in league.draft]
    info = _fetch_player_info(league, list(dict.fromkeys(rostered_ids
                                                         + drafted_ids)))

    rosters = []
    for row, team in enumerate(league.teams):
        players = []
        for player in team.roster:
            entry = info.get(player.playerId)
            origin = dict(acquisition=player.acquisitionType or "",
                          team_row=row, lineup_slot=player.lineupSlot)
            # not in the kona payload: keep him, without ownership info
            players.append(_entry_player(entry, year, **origin) if entry
                           else _roster_player(player, year, **origin))
        rosters.append(players)

    free_agents = [_entry_player(entry, year)
                   for entry in _fetch_free_agent_entries(league, fa_size)]
    picks = _build_picks(league, info, year) if league.draft else []
    drafted_players = {pid: _entry_player(info[pid], year)
                       for pid in drafted_ids if pid in info}
    return RosterReviewData(
        rosters=rosters,
        free_agents=free_agents,
        picks=picks,
        drafted_players=drafted_players,
        counters=_fetch_transaction_counts(league),
        blend_weight=_blend_weight(league),
        slot_counts=slot_counts,
        n_teams=len(league.teams),
    )
