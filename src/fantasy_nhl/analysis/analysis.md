# analysis

The fantasy-hockey logic: everything that is computed from league data,
as plain functions of records, arrays and DataFrames. What the numbers
mean is in [docs/methodology.md](../../../docs/methodology.md); this file
is about the code.

## Boundaries

- Pure: no network, no files, no printing, no prompts.
- Imports nothing of ESPN (`espn_api`, `sources`), of the front ends
  (`views`, `cli`, `api`), of `rich`/`questionary` or of `matplotlib`. The
  only import from the rest of the package is `Category` from
  [config.py](../config.py). Checked by
  [tests/test_layering.py](../../../tests/test_layering.py).
- Everything public is re-exported by [`__init__.py`](__init__.py): the
  other layers write `from ..analysis import name`, the modules in here
  import each other directly.

## Layout

| File | Holds |
| --- | --- |
| [models.py](models.py) | The records (`PreviewPlayer`, `RosterPlayer`, `DraftPick`, `TransactionCounts`), the category sets and `position_group` |
| [rates.py](rates.py) | Per-game rates of a player: `StatBasis`, `player_rate`, the season/projection blend, the minimum games for a Score |
| [ranking.py](ranking.py) | Rank statistics: percentile ranks |
| [standings.py](standings.py) | Round-robin scoring of a week, its timelines, luck, category win rates and contestedness, weekly awards |
| [seats.py](seats.py) | Lineup seats: who can play when, open seats per day and slot, saved-lineup game counts, streaming candidates, coverage by NHL team |
| [schedule.py](schedule.py) | The NHL schedule per fantasy matchup: games, off-nights, effective-games scores and their calibration |
| [preview.py](preview.py) | Predicted category scores of a matchup week |
| [draft.py](draft.py) | Draft picks against ADP, per-team summary, the rosters as drafted |
| [outlook.py](outlook.py) | Projected full-season category totals per roster, replacement-level fill, their round-robin outlook |
| [values.py](values.py) | Player value: `Score`, category rates, percentiles and profiles |
| [review.py](review.py) | The roster-review tables: player table, origins, draft return, acquisitions, drop candidates |

## Key concepts

- **Team rows.** A fantasy team is its row index in
  `LeagueData.team_names`; every per-team list and array is in that order.
  Group by row, never by team name: names can repeat.
- **Player records.** A `PreviewPlayer` carries `season_stats` and
  `projected_stats` as raw totals keyed by ESPN stat name, including the
  games (`GP` for skaters, `GS` for goalies), and only the lineup slots
  that are active in the league. `RosterPlayer` adds ownership, origin and
  the current slot (Bench and IR included). `player_id` 0 means unknown.
- **One entry point for rates.** `player_rate(player, stat, basis)` is the
  only way to get a per-game rate; for the ratio categories
  (`RATIO_CATEGORIES`: GAA, SV%) it returns the ratio itself. The
  `StatBasis` says whether the rate blends season and projection or uses
  the season alone, and every function that rates a player takes one. The
  category outlook is the exception: it is always blended and takes the
  blend weight as a number.
- **Position groups.** `position_group` gives F, D or G by lineup
  eligibility (goalie beats defense). Scores and percentiles are ranked
  within the group; `GOALIE_CATEGORIES` separates the categories only
  goalies produce.
- **Lineup seats.** Who gets a seat on a day is a maximum matching of the
  players whose NHL team plays to the lineup slots (`max_lineup_seats`).
  `open_seat_counts` returns the open skater and goalie seats per scoring
  period; `position_open_seats` splits them by slot, filling the specific
  slots before Forward and Util.
- **Scoring periods.** Days are ESPN scoring period ids (integers); which
  NHL teams play on one is `playing_by_period`, which periods a matchup
  has is `week_periods`. Both come from the ESPN layer, see
  [espn.md](../sources/espn/espn.md).

## Extending

- Add the function to the module of its topic, re-export it in
  `__init__.py`, and test it in
  [tests/test_analysis.py](../../../tests/test_analysis.py).
- Tunable constants are module-level names in capitals with a comment on
  where the value comes from (`MIN_SCORE_GAMES`, `SEAT_CAP`,
  `COMBINED_PLAYOFF_WEIGHT`, ...). If a constant is part of a definition the
  user sees, describe it in the methodology doc as well.

## Gotchas

- A list containing `None` assigned into a float column raises a pandas
  warning, and the tests run with warnings as errors: wrap it in
  `pd.array(values, dtype=float)`.
- `blended_ratio` ignores a split without games: ESPN reports a GAA of 0.0
  for a goalie who has not started, which would rank best.
- Missing data stays missing (`None`/`NaN`); it is never replaced by a
  projection in season-only mode or by a default.

## Tests

[tests/test_analysis.py](../../../tests/test_analysis.py) tests the
functions directly; the golden transcripts exercise them through the views
(see [tests.md](../../../tests/tests.md)).
