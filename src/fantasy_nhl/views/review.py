"""What the player, roster and draft views share: one valued player pool
built from a roster-review fetch, and the legends below their tables."""
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd

from ..analysis import (
    ELITE_PCT,
    GOALIE_CATEGORIES,
    HOLE_PCT,
    PEAK_CATS,
    SPEC_HIGH,
    SPEC_LOW,
    TIER_ELITE,
    TIER_SOLID,
    RosterPlayer,
    StatBasis,
    category_profiles,
    draft_pick_table,
    player_table,
    player_values,
    season_totals,
)
from ..config import Category
from .common import NO_PROJECTION_NOTE, basis_label
from .model import INFO, Note, note

if TYPE_CHECKING:
    from ..sources.espn import LeagueData, RosterReviewData


@dataclass
class ReviewContext:
    data: "LeagueData"
    review: "RosterReviewData"
    basis: StatBasis
    pool: dict[int, RosterPlayer]  # rostered, free agents and drafted, by id
    values: pd.DataFrame  # player_values of the pool
    pick_table: pd.DataFrame | None  # draft_pick_table, None if not drafted
    # category_profiles of the pool, all indexed by player id
    rates: pd.DataFrame
    pcts: pd.DataFrame
    profile: pd.DataFrame
    totals: pd.DataFrame  # season_totals of the pool
    info: pd.DataFrame  # player_table of the pool, indexed by player id

    @property
    def cats(self) -> list[Category]:
        return self.data.config.categories

    @property
    def n_teams(self) -> int:
        return self.review.n_teams

    @property
    def drafted(self) -> bool:
        return self.pick_table is not None

    @property
    def basis_short(self) -> str:
        return "this season" if self.basis.season_only else "blended"

    def group_cats(self, goalies: bool) -> list[str]:
        return [cat.name for cat in self.cats
                if (cat.name in GOALIE_CATEGORIES) == goalies]

    def score_legend(self, *shown: pd.DataFrame,
                     gap: bool = False) -> list[Note]:
        """Score legend; ``shown`` = the player tables it follows."""
        required = self.basis.min_games
        notes = [note(
            f"Score = mean over categories of the rank-based z of the "
            f"per-game rate within the {len(self.pool)}-player pool and the "
            f"player's position group (F / D / G; stats: "
            f"{basis_label(self.basis)}"
            + (f"; blank under {required} GP" if required else "") + ")"
            + ("; Gap = roster% percentile - Score percentile within the "
               "group (+ = crowd overrates)" if gap else "")
            + ". ESPN values as of today.", level=INFO)]
        if any(table["NoProj"].any() for table in shown):
            notes.append(note(NO_PROJECTION_NOTE, level=INFO))
        return notes

    def profile_legend(self, shown: pd.DataFrame) -> list[Note]:
        return [note(
            f"Percentile = rank of the per-game rate within the player's "
            f"position group (F / D / G) of the {len(self.pool)}-player pool "
            f"(100 = best, inverted categories flipped). Level = Score "
            f"percentile within the group; Spec = Peak - Breadth, where "
            f"Peak = mean percentile of the best {PEAK_CATS} categories and "
            f"Breadth = mean of the rest; Elite = categories >= {ELITE_PCT}, "
            f"Holes = categories <= {HOLE_PCT}. Type = Elite (Level >= "
            f"{TIER_ELITE}) / Solid (>= {TIER_SOLID}) / Depth, + specialist "
            f"(Spec >= {SPEC_HIGH}) or all-rounder (Spec <= {SPEC_LOW}); "
            f"shape, not extra value.", level=INFO),
            *self.score_legend(shown)]


def build_review_context(data: "LeagueData", review: "RosterReviewData",
                         basis: StatBasis) -> ReviewContext:
    """Value every player of a roster-review fetch on the given stats."""
    cats = data.config.categories
    pool: dict[int, RosterPlayer] = {}
    for player in [p for r in review.rosters for p in r] + review.free_agents:
        pool[player.player_id] = player
    for pid, player in review.drafted_players.items():
        pool.setdefault(pid, player)
    values = player_values(list(pool.values()), cats, basis)
    pick_table = (draft_pick_table(review.picks, data.team_names,
                                   review.n_teams)
                  if review.picks else None)
    rates, pcts, profile = category_profiles(list(pool.values()), cats, basis)
    totals = season_totals(list(pool.values()), cats)
    info = player_table(pool.values(), values, data.team_names)
    info.index = profile.index
    return ReviewContext(data, review, basis, pool, values, pick_table,
                         rates, pcts, profile, totals, info)
