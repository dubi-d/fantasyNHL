"""Player and draft records, and how players group by position."""
from dataclasses import dataclass, field


# categories that are per-game ratios (averaged by goalie games, not summed)
RATIO_CATEGORIES = frozenset({"GAA", "SV%"})

# categories only goalies produce (ESPN stat labels)
GOALIE_CATEGORIES = frozenset(
    {"GA", "GAA", "SA", "SV", "SV%", "SO", "GS", "W", "L", "OTL", "MIN ?"})

_GOALIE_SLOT = "Goalie"


@dataclass
class PreviewPlayer:
    """Roster player input for matchup previews (active players only).

    Stat dicts are raw season/projection totals keyed by ESPN stat name,
    including games played ('GP' for skaters, 'GS' for goalies).
    """
    name: str
    pro_team: str
    eligible_slots: list[str]  # active lineup slots only (no Bench/IR)
    season_stats: dict[str, float] = field(default_factory=dict)
    projected_stats: dict[str, float] = field(default_factory=dict)
    injury: str = ""  # ESPN injuryStatus (empty = fine/unknown)
    player_id: int = 0  # stable identity for date-specific saved lineups


@dataclass
class DraftPick:
    """One draft pick joined with ESPN's current info on the player."""
    team_row: int  # drafting fantasy team (LeagueData row)
    round: int
    pick_in_round: int
    overall: int
    player_id: int
    name: str
    position: str  # ESPN default position name (e.g. "Goalie")
    eligible_slots: list[str] = field(default_factory=list)  # no Bench/IR
    adp: float | None = None  # ESPN average draft position (None = unknown)
    pct_owned: float | None = None  # ESPN roster% today
    pct_change: float | None = None  # ESPN roster% change over 7 days
    espn_rank: int | None = None  # ESPN standard draft rank
    projected_stats: dict[str, float] = field(default_factory=dict)
    rostered_by: int | None = None  # fantasy team row today (None = free agent)


@dataclass
class RosterPlayer(PreviewPlayer):
    """A rostered or free-agent player with ESPN's ownership and origin
    info (all lineup slots, including Bench and IR)."""
    position: str = ""  # ESPN default position name
    acquisition: str = ""  # DRAFT / ADD / TRADE ("" for free agents)
    team_row: int | None = None  # fantasy team row (None = free agent)
    lineup_slot: str = ""  # current slot name ("" for free agents)
    pct_owned: float | None = None
    pct_change: float | None = None  # 7-day roster% change
    espn_rank: int | None = None
    adp: float | None = None


@dataclass
class TransactionCounts:
    """A fantasy team's season-to-date transaction counters."""
    adds: int = 0
    drops: int = 0
    trades: int = 0


_IR_SLOT = "IR"
_DEFENSE_SLOT = "Defense"
ACQUIRED_DRAFT = "DRAFT"
ACQUIRED_ADD = "ADD"
ACQUIRED_TRADE = "TRADE"
POSITION_GROUPS = ("F", "D", "G")


def position_group(player: PreviewPlayer) -> str:
    """'F', 'D' or 'G' by lineup eligibility (goalie beats defense)."""
    if _GOALIE_SLOT in player.eligible_slots:
        return "G"
    return "D" if _DEFENSE_SLOT in player.eligible_slots else "F"
