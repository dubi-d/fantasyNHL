"""Shared offline test support: lookup/patch helpers that keep working when
package modules move, and a deterministic synthetic league whose methods
stand in for the ESPN fetchers."""
import importlib
import pkgutil
import sys
from dataclasses import replace
from datetime import date, timedelta

import numpy as np

import fantasy_nhl
from fantasy_nhl.analysis import (
    DraftPick,
    PreviewPlayer,
    RosterPlayer,
    TransactionCounts,
    matchup_result,
)
from fantasy_nhl.config import Category, LeagueConfig, ScheduleCalibration


def package_modules() -> list:
    """Every module of the package, imported."""
    for info in pkgutil.walk_packages(fantasy_nhl.__path__, "fantasy_nhl."):
        importlib.import_module(info.name)
    return [module for name, module in sorted(sys.modules.items())
            if name.split(".")[0] == "fantasy_nhl"]


def lookup(name: str):
    """The package-level object of that name, wherever it is defined."""
    for module in package_modules():
        if name in vars(module):
            return vars(module)[name]
    raise LookupError(name)


def patch_everywhere(monkeypatch, name: str, value) -> int:
    """Replace ``name`` in every package module that binds it (the defining
    module and all ``from x import name`` copies); returns the hit count."""
    hits = [module for module in package_modules() if name in vars(module)]
    for module in hits:
        monkeypatch.setattr(module, name, value)
    return len(hits)


TEAM_NAMES = ["Alpha", "Bravo", "Charlie", "Delta"]
CATEGORIES = [Category("G"), Category("A"), Category("PPP"), Category("HIT"),
              Category("GAA", inverted=True), Category("SV%")]
NHL_TEAMS = ["ANA", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL", "DAL",
             "DET", "EDM", "FLA", "LA", "MIN", "MTL", "NJ", "NSH", "NYI",
             "NYR", "OTT"]
SLOT_COUNTS = {"Center": 1, "Left Wing": 1, "Right Wing": 1, "Forward": 1,
               "Defense": 2, "Goalie": 1, "Util": 1}
TOTAL_WEEKS = 8
REGULAR_WEEKS = 6
DAYS_PER_WEEK = 7
SEASON_START = date(2026, 10, 5)  # a Monday
PAIRINGS = {1: [(0, 1), (2, 3)], 2: [(0, 2), (1, 3)], 3: [(0, 3), (1, 2)],
            4: [(0, 1), (2, 3)], 5: [(0, 2), (1, 3)], 6: [(0, 3), (1, 2)],
            7: [(0, 1), (2, 3)], 8: [(0, 2), (1, 3)]}

# kind -> (ESPN position, eligible lineup slots)
_KINDS = {
    "C": ("Center", ["Center", "Forward", "Util"]),
    "LW": ("Left Wing", ["Left Wing", "Forward", "Util"]),
    "RW": ("Right Wing", ["Right Wing", "Forward", "Util"]),
    "CW": ("Center", ["Center", "Left Wing", "Forward", "Util"]),
    "D": ("Defense", ["Defense", "Util"]),
    "G": ("Goalie", ["Goalie"]),
}
# one roster: (kind, lineup slot, acquisition) by roster index
_ROSTER = [("C", "Center", "DRAFT"), ("C", "Forward", "DRAFT"),
           ("LW", "Left Wing", "DRAFT"), ("RW", "Right Wing", "ADD"),
           ("CW", "Util", "TRADE"), ("D", "Defense", "DRAFT"),
           ("D", "Defense", "ADD"), ("D", "Bench", "DRAFT"),
           ("G", "Goalie", "DRAFT"), ("G", "Bench", "ADD"),
           ("RW", "IR", "ADD")]
# exceptions by (team row, roster index)
_INJURIES = {(0, 1): "DAY_TO_DAY", (0, 10): "INJURY_RESERVE", (1, 3): "OUT",
             (1, 10): "OUT", (2, 2): "SUSPENSION", (2, 10): "INJURY_RESERVE",
             (3, 5): "QUESTIONABLE", (3, 6): ""}
_GAMES = {(0, 3): 0, (1, 6): 3, (3, 9): 0}
_UNPROJECTED = {(1, 9), (2, 4), (3, 2)}
_NAMES = {(1, 2): "Twin"}
_HIDDEN_ID = 307  # previews report this player without an id

_FA_COUNT = 40
_FA_SKATERS = ["C", "LW", "D", "RW", "CW", "D"]
_FA_INJURIES = {4: "DAY_TO_DAY", 9: "OUT", 13: "SUSPENSION"}
_FA_GAMES = {5: 0, 10: 2}
_FA_UNPROJECTED = {3, 11, 17}
_FA_NAMES = {0: "Twin", 8: "Twin"}


class _Lcg:
    """Tiny deterministic generator, independent of numpy's streams."""

    def __init__(self, seed: int) -> None:
        self._state = seed

    def below(self, n: int) -> int:
        self._state = (self._state * 1103515245 + 12345) % 2**31
        return (self._state >> 8) % n


def _stats(rng: _Lcg, kind: str, games: int) -> dict[str, float]:
    if kind == "G":
        if not games:
            return {"GS": 0, "GAA": 0.0, "SV%": 0.0}  # ESPN's placeholders
        return {"GS": games, "W": games * (30 + rng.below(40)) // 100,
                "GAA": round(2.1 + rng.below(130) / 100, 2),
                "SV%": round(0.885 + rng.below(40) / 1000, 3)}
    if not games:
        return {}
    hits = (70 if kind == "D" else 20) + rng.below(180)
    return {"GP": games, "G": games * (4 + rng.below(40)) // 100,
            "A": games * (10 + rng.below(60)) // 100,
            "PPP": games * rng.below(35) // 100, "HIT": games * hits // 100}


def _player(rng: _Lcg, pid: int, name: str, kind: str, games: int, *,
            projected: bool = True, injury: str = "ACTIVE",
            **origin) -> RosterPlayer:
    position, slots = _KINDS[kind]
    full_season = (35 if kind == "G" else 62) + rng.below(21)
    return RosterPlayer(
        name=name, pro_team=NHL_TEAMS[rng.below(len(NHL_TEAMS))],
        eligible_slots=list(slots),
        season_stats=_stats(rng, kind, games),
        projected_stats=_stats(rng, kind, full_season) if projected else {},
        injury=injury, player_id=pid, position=position,
        pct_owned=round(rng.below(1000) / 10, 1),
        pct_change=round(rng.below(200) / 10 - 10, 1),
        espn_rank=1 + rng.below(300),
        adp=round(41 + rng.below(1500) / 10, 1), **origin)


def _rosters(rng: _Lcg, trades: bool) -> list[list[RosterPlayer]]:
    rosters = []
    for row, team in enumerate(TEAM_NAMES):
        counts: dict[str, int] = {}
        roster = []
        for k, (kind, slot, acquisition) in enumerate(_ROSTER):
            counts[kind] = counts.get(kind, 0) + 1
            if acquisition == "TRADE" and not trades:
                acquisition = "ADD"
            roster.append(_player(
                rng, 100 * (row + 1) + k + 1,
                _NAMES.get((row, k), f"{team} {kind}{counts[kind]}"), kind,
                _GAMES.get((row, k), 8 + rng.below(18)),
                projected=(row, k) not in _UNPROJECTED,
                injury=_INJURIES.get((row, k), "ACTIVE"),
                acquisition=acquisition, team_row=row, lineup_slot=slot))
        rosters.append(roster)
    return rosters


def _free_agents(rng: _Lcg) -> list[RosterPlayer]:
    agents = []
    counts: dict[str, int] = {}
    skaters = 0
    for i in range(_FA_COUNT):
        if i % 5 == 2:
            kind = "G"
        else:
            kind = _FA_SKATERS[skaters % len(_FA_SKATERS)]
            skaters += 1
        counts[kind] = counts.get(kind, 0) + 1
        player = _player(rng, 900 + i,
                         _FA_NAMES.get(i, f"Free {kind}{counts[kind]}"), kind,
                         _FA_GAMES.get(i, 6 + rng.below(20)),
                         projected=i not in _FA_UNPROJECTED,
                         injury=_FA_INJURIES.get(i, "ACTIVE"))
        player.pct_owned = round(64 - 2.1 * i, 1)  # most-owned first
        agents.append(player)
    return agents


def _draft(rng: _Lcg, rosters: list[list[RosterPlayer]],
           free_agents: list[RosterPlayer], constant_adp: bool,
           ) -> tuple[list[DraftPick], dict[int, RosterPlayer]]:
    """Ten snake rounds: per team six kept picks, one traded away, two
    dropped to free agency and one who left the player pool."""
    gone = [_player(rng, 801, "Dropped C1", "C", 12),
            _player(rng, 802, "Dropped G1", "G", 4),
            None,  # ESPN has no info on this pick at all
            free_agents[9]]
    by_team = []
    for row in range(len(TEAM_NAMES)):
        drafted = ([p for p in rosters[row] if p.acquisition == "DRAFT"]
                   + [p for p in rosters[(row + 1) % len(TEAM_NAMES)]
                      if p.acquisition == "TRADE"]
                   + free_agents[2 * row + 1:2 * row + 3] + [gone[row]])
        turn = rng.below(len(drafted))
        by_team.append(drafted[turn:] + drafted[:turn])

    picks = []
    drafted_players = {}
    for rnd in range(1, len(by_team[0]) + 1):
        order = list(range(len(TEAM_NAMES)))
        if rnd % 2 == 0:
            order.reverse()
        for slot, row in enumerate(order, start=1):
            overall = (rnd - 1) * len(TEAM_NAMES) + slot
            player = by_team[row][rnd - 1]
            if player is None:
                picks.append(DraftPick(row, rnd, slot, overall, 803,
                                       "Ghost Pick", ""))
                continue
            player.adp = (230.0 if constant_adp else
                          max(1.0, round(overall
                                         + (rng.below(25) - 12) * 1.5, 1)))
            if overall == 17 and not constant_adp:
                player.adp = 0.0  # ESPN's "never drafted" value
            picks.append(DraftPick(
                team_row=row, round=rnd, pick_in_round=slot, overall=overall,
                player_id=player.player_id, name=player.name,
                position=player.position,
                eligible_slots=list(player.eligible_slots), adp=player.adp,
                pct_owned=player.pct_owned, pct_change=player.pct_change,
                espn_rank=player.espn_rank,
                projected_stats=player.projected_stats,
                rostered_by=player.team_row))
            drafted_players[player.player_id] = replace(
                player, acquisition="", team_row=None, lineup_slot="")
    return picks, drafted_players


def _week_scores(rng: _Lcg, scale: float) -> list[list[float]]:
    return [[round((8 + rng.below(12)) * scale),
             round((14 + rng.below(16)) * scale),
             round((4 + rng.below(9)) * scale),
             round((60 + rng.below(70)) * scale),
             round(2.0 + rng.below(140) / 100, 2),
             round(0.895 + rng.below(30) / 1000, 3)] for _ in TEAM_NAMES]


def _plays(index: int, period: int) -> bool:
    weekday = (period - 1) % DAYS_PER_WEEK  # 0 = Monday
    if period == 17:
        return False  # a night without games
    if weekday in (1, 3, 5):
        return (index + period) % 10 != 0  # 18 teams: a busy night
    if weekday in (0, 4):
        return (index + period) % 5 < 2
    if weekday == 2:
        return (index * 3 + period) % 5 == 0
    return (index + 2 * period) % 3 == 0


def _playing(period: int) -> set[str]:
    return {team for i, team in enumerate(NHL_TEAMS) if _plays(i, period)}


def _preview_player(player: RosterPlayer) -> PreviewPlayer:
    return PreviewPlayer(
        name=player.name, pro_team=player.pro_team,
        eligible_slots=[s for s in player.eligible_slots if s in SLOT_COUNTS],
        season_stats=player.season_stats,
        projected_stats=player.projected_stats, injury=player.injury,
        player_id=0 if player.player_id == _HIDDEN_ID else player.player_id)


class FakeLeague:
    """A synthetic league: ``data`` (a real LeagueData) plus one method per
    ESPN fetcher, named and called like the fetcher it replaces."""

    FETCHERS = ("fetch_schedule_data", "fetch_week_dates",
                "fetch_week_pairings", "fetch_preview_data",
                "fetch_adds_used", "fetch_ir_roster",
                "fetch_daily_lineup_slots", "fetch_free_agents",
                "fetch_rosters_and_slots", "fetch_roster_review",
                "fetch_calibration_data")

    def __init__(self, *, current_week: int = 5, today: int = 31,
                 season_over: bool = False, drafted: bool = True,
                 rostered: bool = True, free_agents: bool | None = None,
                 constant_adp: bool = False,
                 empty_rosters: tuple[int, ...] = (), trades: bool = True,
                 season_stats: bool = True, blend_weight: float = 0.3,
                 add_limit: int | None = 4,
                 calibration: ScheduleCalibration | None = None) -> None:
        """
        :param current_week: ongoing matchup (the last one when season_over)
        :param today: current scoring period
        :param season_over: the current matchup has a decided result
        :param drafted: the league has a draft on record
        :param rostered: the teams have rosters
        :param free_agents: free agents exist (default: as ``rostered``)
        :param constant_adp: ESPN's archived placeholder ADP for every pick
        :param empty_rosters: team rows without any player
        :param trades: some players were acquired by trade
        :param season_stats: players have current-season stats
        :param blend_weight: share of the season elapsed
        :param add_limit: weekly acquisition limit (None = unlimited)
        :param calibration: stored schedule-scoring calibration
        """
        self.today = today
        self.blend_weight = blend_weight
        self.add_limit = add_limit
        self.adds_used = [2, None, 0, 5]
        self._season_over = season_over
        self.config = LeagueConfig(
            name="Test League", league_id=1, year=2027, swid="{SWID}",
            espn_s2="S2", categories=CATEGORIES, calibration=calibration,
            default=True)
        # the leagues offered as calibration source (stands in for load_config)
        self.sources = [LeagueConfig(name="Old League", league_id=2,
                                     year=2026, swid="{SWID}", espn_s2="S2",
                                     categories=CATEGORIES), self.config]

        periods = range(1, TOTAL_WEEKS * DAYS_PER_WEEK + 1)
        self.schedule = lookup("ScheduleData")(
            playing_by_period={p: _playing(p) for p in periods},
            period_dates={p: SEASON_START + timedelta(days=p - 1)
                          for p in periods},
            week_periods={w: list(range((w - 1) * DAYS_PER_WEEK + 1,
                                        w * DAYS_PER_WEEK + 1))
                          for w in range(1, TOTAL_WEEKS + 1)})

        rng = _Lcg(2026)
        decided = current_week if season_over else current_week - 1
        scores = np.zeros((len(TEAM_NAMES), len(CATEGORIES), current_week))
        for week in range(decided):
            scores[:, :, week] = _week_scores(rng, 1.0)
        if decided > 1:
            scores[3, 0, 1] = scores[1, 0, 1]  # a tied category in a matchup
        if not season_over and today > self.schedule.week_periods[current_week][0]:
            scores[:, :, -1] = _week_scores(rng, 0.4)
            scores[1, 4, -1] = np.inf  # ESPN's GAA before the first start
        results = [["NA"] * current_week for _ in TEAM_NAMES]
        for week in range(1, decided + 1):
            for home, away in PAIRINGS[week]:
                won, lost, _, _ = matchup_result(
                    scores[home, :, week - 1], scores[away, :, week - 1],
                    CATEGORIES)
                results[home][week - 1] = "W" if won else "L" if lost else "T"
                results[away][week - 1] = "L" if won else "W" if lost else "T"
        names = list(TEAM_NAMES)
        if season_over:
            names[2] += " *"  # the champion's marker
        self.data = lookup("LeagueData")(
            config=self.config, team_names=names, current_week=current_week,
            weekly_cat_scores=scores, weekly_results=results,
            total_weeks=TOTAL_WEEKS, regular_weeks=REGULAR_WEEKS)

        rosters = _rosters(rng, trades) if rostered else [[] for _ in names]
        for row in empty_rosters:
            rosters[row] = []
        pool = rostered if free_agents is None else free_agents
        free_agents = _free_agents(rng) if pool else []
        picks, drafted_players = (
            _draft(rng, rosters, free_agents, constant_adp)
            if drafted and rostered else ([], {}))
        if not season_stats:
            for player in ([p for roster in rosters for p in roster]
                           + free_agents + list(drafted_players.values())):
                player.season_stats = {}
        self.review = lookup("RosterReviewData")(
            rosters=rosters, free_agents=free_agents, picks=picks,
            drafted_players=drafted_players,
            counters=[TransactionCounts(12, 11, 2), TransactionCounts(7, 7, 1),
                      TransactionCounts(25, 24, 3), TransactionCounts(4, 4, 0)],
            blend_weight=blend_weight, slot_counts=dict(SLOT_COUNTS),
            n_teams=len(names))

    def _pairings(self, week: int) -> list[tuple[int, int]]:
        seeded = self._season_over or week <= REGULAR_WEEKS
        return list(PAIRINGS[week]) if seeded else []

    def _preview_rosters(self) -> list[list[PreviewPlayer]]:
        return [[_preview_player(p) for p in roster if p.lineup_slot != "IR"]
                for roster in self.review.rosters]

    def fetch_schedule_data(self, data):
        return self.schedule

    def fetch_week_dates(self, data):
        dates = self.schedule.period_dates
        data.week_dates = {week: (dates[min(ps)], dates[max(ps)])
                           for week, ps in self.schedule.week_periods.items()}
        return data.week_dates

    def fetch_week_pairings(self, data, week):
        return self._pairings(week)

    def fetch_preview_data(self, data, week):
        periods = self.schedule.week_periods[week]
        following = self.schedule.week_periods.get(week + 1, [])
        remaining = [p for p in periods if p >= self.today]
        elapsed = len(periods) - len(remaining)
        goalie_games = np.full(len(TEAM_NAMES), float(min(elapsed, 2)))
        if week == data.current_week and not self._season_over:
            goalie_games[1] = 0  # matches the GAA placeholder above
        playing = self.schedule.playing_by_period
        started = (set(sorted(playing[self.today])[:2])
                   if self.today in periods else set())
        dates = self.schedule.period_dates
        return lookup("PreviewData")(
            week=week, pairings=self._pairings(week),
            actual_scores=(data.weekly_cat_scores[:, :, week - 1].copy()
                           if week <= data.current_week
                           else np.zeros((len(TEAM_NAMES), len(CATEGORIES)))),
            rosters=self._preview_rosters(), slot_counts=dict(SLOT_COUNTS),
            playing_by_period=playing, periods=periods,
            remaining_periods=remaining, blend_weight=self.blend_weight,
            actual_games=np.array([5.0, 4.0, 6.0, 5.0]) * elapsed,
            actual_goalie_games=goalie_games,
            start_date=dates[min(periods)], end_date=dates[max(periods)],
            current_period=self.today,
            period_dates={p: dates[p] for p in periods + following},
            add_limit=self.add_limit, next_periods=following,
            started_today=started)

    def fetch_adds_used(self, data, week):
        return list(self.adds_used)

    def fetch_ir_roster(self, data, team_row):
        return [p for p in self.review.rosters[team_row]
                if p.lineup_slot == "IR"]

    def fetch_daily_lineup_slots(self, data, team_row, periods):
        daily = {}
        for period in periods:
            slots = daily[period] = {}
            if period % DAYS_PER_WEEK == 0:
                continue  # a day ESPN returned nothing usable for
            for k, player in enumerate(self.review.rosters[team_row]):
                if (k + period) % 11 == 0:
                    continue  # missing from the payload
                slots[player.player_id] = (
                    "Bench" if (k + period) % 4 == 0
                    else "IR" if (k + period) % 13 == 0
                    else player.lineup_slot)
        return daily

    def fetch_free_agents(self, data, slot_counts, size=100):
        return [_preview_player(p) for p in self.review.free_agents
                if p.position != "Goalie"]

    def fetch_rosters_and_slots(self, data):
        return dict(SLOT_COUNTS), self._preview_rosters()

    def fetch_roster_review(self, data):
        return self.review

    def fetch_calibration_data(self, source):
        return lookup("CalibrationData")(
            rosters=self._preview_rosters(), slot_counts=dict(SLOT_COUNTS),
            playing_by_period=self.schedule.playing_by_period)


# the league in the states the tests look at it

def midseason(**kwargs) -> FakeLeague:
    return FakeLeague(**kwargs)


def finished() -> FakeLeague:
    """The season is over: only the last playoff matchup is left."""
    return FakeLeague(current_week=8, today=60, season_over=True,
                      constant_adp=True, blend_weight=1.0, add_limit=None)


def opening_day() -> FakeLeague:
    return FakeLeague(current_week=1, today=1, season_stats=False,
                      blend_weight=0.0)


def preseason() -> FakeLeague:
    """Nothing there yet: no rosters, no draft, no free agents."""
    return FakeLeague(current_week=1, today=1, rostered=False,
                      blend_weight=0.0)


def pre_draft() -> FakeLeague:
    """Before the draft: empty rosters, but ESPN lists free agents."""
    return FakeLeague(current_week=1, today=1, rostered=False,
                      free_agents=True, season_stats=False, blend_weight=0.0)


def undrafted() -> FakeLeague:
    return FakeLeague(drafted=False, trades=False, empty_rosters=(3,))


SCENARIOS = {factory.__name__: factory for factory in (
    midseason, finished, opening_day, preseason, pre_draft, undrafted)}
