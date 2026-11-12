"""Rosters, lineups, free agents and player info."""
import json

from espn_api.hockey import League
from espn_api.hockey.constant import POSITION_MAP
from espn_api.hockey.player import Player

from ...analysis import PreviewPlayer, RosterPlayer
from .league import LeagueData


def _fetch_roster_settings(league: League) -> tuple[dict[str, int], int | None]:
    """Active lineup slot capacities and weekly add limit from the raw
    settings (the espn_api wrapper does not retain either)."""
    data = league.espn_request.league_get(params={"view": "mSettings"})
    settings = data["settings"]
    raw_counts = settings["rosterSettings"]["lineupSlotCounts"]
    slot_counts = {}
    for slot_id, count in raw_counts.items():
        name = POSITION_MAP.get(int(slot_id))
        if count > 0 and isinstance(name, str) and name not in ("Bench", "IR"):
            slot_counts[name] = count
    limit = settings.get("acquisitionSettings", {}).get("matchupAcquisitionLimit")
    # ESPN reports "no limit" as a negative value
    add_limit = int(limit) if limit is not None and limit >= 0 else None
    return slot_counts, add_limit


def fetch_rosters_and_slots(data: LeagueData,
                            ) -> tuple[dict[str, int],
                                       list[list[PreviewPlayer]]]:
    """Current lineup slots and rosters by team row (one settings request;
    rosters are already on the league session)."""
    league = data.espn_league
    if league is None:
        raise ValueError("LeagueData has no live ESPN session.")
    slot_counts, _ = _fetch_roster_settings(league)
    return slot_counts, _preview_rosters(league, data.config.year, slot_counts)


def fetch_adds_used(data: LeagueData, week: int) -> list[int | None]:
    """Adds already used in the given matchup week per team (by row), from
    the raw transaction counters (not exposed by the espn_api wrapper).
    None where ESPN does not report the counter."""
    league = data.espn_league
    if league is None:
        raise ValueError("LeagueData has no live ESPN session.")
    raw = league.espn_request.league_get(params={"view": "mTeam"})
    used_by_id = {}
    for team in raw.get("teams", []):
        totals = team.get("transactionCounter", {}).get("matchupAcquisitionTotals")
        if isinstance(totals, dict):
            # weeks without any transaction are simply absent
            used_by_id[team["id"]] = totals.get(str(week), totals.get(week, 0))
    return [used_by_id.get(team.team_id) for team in league.teams]


def _preview_player(player, year: int,
                    slot_counts: dict[str, int]) -> PreviewPlayer | None:
    """Build a PreviewPlayer from an espn_api Player, or None if the player
    fits no active lineup slot."""
    eligible = [s for s in player.eligibleSlots if s in slot_counts]
    if not eligible:
        return None
    return PreviewPlayer(
        name=player.name,
        pro_team=player.proTeam,
        eligible_slots=eligible,
        season_stats=player.stats.get(f"Total {year}",
                                      {}).get("total") or {},
        projected_stats=player.stats.get(f"Projected {year}",
                                         {}).get("total") or {},
        injury=getattr(player, "injuryStatus", "") or "",
        player_id=player.playerId,
    )


def _preview_rosters(league: League, year: int,
                     slot_counts: dict[str, int]) -> list[list[PreviewPlayer]]:
    """Current rosters as PreviewPlayers by team row, excluding IR players."""
    rosters = []
    for team in league.teams:
        players = []
        for player in team.roster:
            if player.lineupSlot == "IR":
                continue
            preview = _preview_player(player, year, slot_counts)
            if preview is not None:
                players.append(preview)
        rosters.append(players)
    return rosters


def fetch_ir_roster(data: LeagueData, team_row: int) -> list[RosterPlayer]:
    """Display-only IR players from the same loaded snapshot as the roster.

    Assignment to IR, not injury status, controls membership. No new requests;
    unlike preview players, these rows need not fit an active lineup slot.
    """
    league = data.espn_league
    if league is None:
        raise ValueError("LeagueData has no live ESPN session.")
    return [_roster_player(player, data.config.year,
                           team_row=team_row, lineup_slot="IR")
            for player in league.teams[team_row].roster
            if player.lineupSlot == "IR"]


def fetch_daily_lineup_slots(data: LeagueData, team_row: int,
                            periods: list[int]) -> dict[int, dict[int, str]]:
    """Saved assignments for one team, with one mRoster GET per requested day.

    Date-specific mRoster works independently of matchup pairings (including
    future days). Never substitute the loaded/current roster for missing data.
    Empty or mismatched-date responses stay unknown; request errors propagate.
    """
    if not periods:
        return {}
    league = data.espn_league
    if league is None:
        raise ValueError("LeagueData has no live ESPN session.")
    team_id = league.teams[team_row].team_id
    daily: dict[int, dict[int, str]] = {}
    for period in dict.fromkeys(periods):
        raw = league.espn_request.league_get(
            params={"view": "mRoster", "scoringPeriodId": period})
        slots: dict[int, str] = {}
        daily[period] = slots
        if raw.get("scoringPeriodId") != period:
            continue
        team = next((t for t in (raw.get("teams") or [])
                     if t.get("id") == team_id), {})
        roster = team.get("roster") or {}
        for entry in roster.get("entries") or []:
            player = (entry.get("playerPoolEntry") or {}).get("player") or {}
            player_id = entry.get("playerId") or player.get("id")
            slot = POSITION_MAP.get(entry.get("lineupSlotId"))
            if (isinstance(player_id, int) and player_id > 0
                    and isinstance(slot, str)):
                slots[player_id] = slot
    return daily


def fetch_free_agents(data: LeagueData, slot_counts: dict[str, int],
                      size: int = 100) -> list[PreviewPlayer]:
    """Skater free agents in ESPN ownership order (most-owned first),
    excluding goalies. Injury status is passed through."""
    league = data.espn_league
    if league is None:
        raise ValueError("LeagueData has no live ESPN session.")
    agents = []
    # the Util slot filter matches all skaters but no goalies
    for fa in league.free_agents(week=league.scoringPeriodId, size=size,
                                 position="Util"):
        player = _preview_player(fa, data.config.year, slot_counts)
        if player is not None and "Goalie" not in player.eligible_slots:
            agents.append(player)
    return agents


# ids per kona_player_info request (238 in one request worked live; 200
# leaves a margin under whatever header size ESPN tolerates)
_PLAYER_INFO_CHUNK = 200


def _fetch_player_pool(league: League, player_filter: dict) -> list[dict]:
    """Raw kona_player_info entries (ownership, draft ranks, stat splits)
    matching an x-fantasy-filter 'players' clause."""
    # a limit without a sort key makes ESPN answer HTTP 400
    filters = {"players": {
        **player_filter,
        "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}}
    raw = league.espn_request.league_get(
        params={"view": "kona_player_info",
                "scoringPeriodId": league.scoringPeriodId},
        headers={"x-fantasy-filter": json.dumps(filters)})
    return raw.get("players", [])


def _fetch_player_info(league: League, player_ids: list[int]) -> dict[int, dict]:
    """Raw entries by player id, for rostered and free-agent players alike."""
    info: dict[int, dict] = {}
    for start in range(0, len(player_ids), _PLAYER_INFO_CHUNK):
        chunk = player_ids[start:start + _PLAYER_INFO_CHUNK]
        for entry in _fetch_player_pool(
                league, {"filterIds": {"value": chunk}, "limit": len(chunk)}):
            info[entry["id"]] = entry
    return info


def _fetch_free_agent_entries(league: League, size: int) -> list[dict]:
    """The most-owned free agents (skaters and goalies), raw entries."""
    return _fetch_player_pool(
        league, {"filterStatus": {"value": ["FREEAGENT", "WAIVERS"]},
                 "limit": size})


def _blend_weight(league: League) -> float:
    """Weight of current-season rates vs projections: season fraction elapsed."""
    season_span = league.finalScoringPeriod - league.firstScoringPeriod
    elapsed = league.scoringPeriodId - league.firstScoringPeriod
    return min(max(elapsed / season_span if season_span else 1.0, 0.0), 1.0)


def _roster_player(player: Player, year: int, raw_player: dict | None = None,
                   **origin) -> RosterPlayer:
    """Build a RosterPlayer from an espn_api Player plus, when available,
    the raw kona player dict (ownership, draft ranks); origin fields
    (acquisition, team_row, lineup_slot) come from the roster."""
    raw_player = raw_player or {}
    ownership = raw_player.get("ownership") or {}
    rank = (raw_player.get("draftRanksByRankType") or {}).get("STANDARD", {})
    return RosterPlayer(
        name=player.name,
        pro_team=player.proTeam,
        eligible_slots=[s for s in player.eligibleSlots
                        if s not in ("Bench", "IR")],
        season_stats=player.stats.get(f"Total {year}", {}).get("total") or {},
        projected_stats=player.stats.get(f"Projected {year}",
                                         {}).get("total") or {},
        injury=player.injuryStatus or "",
        player_id=player.playerId,
        position=player.position,
        pct_owned=ownership.get("percentOwned"),
        pct_change=ownership.get("percentChange"),
        espn_rank=rank.get("rank"),
        adp=ownership.get("averageDraftPosition"),
        **origin,
    )


def _entry_player(entry: dict, year: int, **origin) -> RosterPlayer:
    """RosterPlayer from a raw kona entry."""
    return _roster_player(Player(entry), year, entry["player"], **origin)
