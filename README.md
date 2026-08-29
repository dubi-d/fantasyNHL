# fantasyNHL

My repo for playing around with stats in my fantasy hockey league.
Uses [cwendt94/espn-api](https://github.com/cwendt94/espn-api).

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

The `[dev]` extra adds the development dependencies (pytest) so the test
suite runs out of the box; for just using the CLI, `pip install -e .`
is enough.

## Configuration

Leagues and their scoring categories live in [config.yaml](config.yaml)
(committed). ESPN credentials (SWID / espn_s2 cookies) live in `secrets.yaml`
(gitignored), keyed by league name — copy
[secrets.example.yaml](secrets.example.yaml) to `secrets.yaml` and fill in
your cookies. Add or replace leagues as entries under `leagues:` plus a matching
entry in `secrets.yaml`.

## Usage

```bash
.venv/bin/fantasy-nhl
```

Starts an interactive session: pick a league and tools from arrow-key menus.
League data is fetched once per session and reused.

## Tools

- **Show weekly scores** — For each matchup week (including the ongoing one),
  prints a round-robin table: every team is matched against every other team
  using their category totals of that week, yielding W/L/T, categories won,
  and points (2 per win, 1 per tie). A `Result` column shows the team's actual
  ESPN matchup outcome that week (`NA` while undecided), and a `Luck` column
  quantifies that week's schedule luck (see below; empty while the matchup is
  undecided). Sorted by points, indexed by rank.
- **Show accumulated scores** — Sums the weekly round-robin results over all
  completed weeks into overall standings, sorted by round-robin strength and
  indexed by rank. The actual matchup record (W/L/T) and points (`Pts`) are
  shown next to the team name, separated from the round-robin stats
  (`rrW/rrL/rrT`) and the expected points (`xPts`, see below). Useful as
  a schedule-independent measure of season-long team strength. A `Luck`
  column shows the accumulated schedule luck.
- **Show luck ranking** — Ranks teams by accumulated schedule luck over all
  completed weeks, luckiest first, alongside their actual record, actual
  points and expected points.
- **Show power rankings over time** — Round-robin points per completed
  matchup as a terminal heatmap, plus a shareable two-panel PNG saved to
  `plots/`: a "who's hot" bump chart ranking teams by their round-robin
  points over a trailing window of matchups (window prompted, default 4),
  and a "season strength" line chart of expected points per matchup
  (accumulated `xPts` divided by matchups played, so 2 = would beat
  everyone, 1 = league average).
- **Show category strength profile** — For each team, the win rate per
  category across all completed weeks' round-robin comparisons (ties count as
  half a win, so each column averages 0.5 across the league). Values near 1
  are structural strengths, values near 0 are weaknesses. An
  `Overall` column averages across categories and sorts the table; a
  `(contested)` footer row shows how up-for-grabs each category is
  league-wide (see below).
- **Show matchup preview** — Predicted category scores for every head-to-head
  pairing of a selected matchup. Elapsed days use real data (live scores and
  games actually played), remaining days use blended per-game rates (see
  below) with the current roster filling all active lineup slots against the
  NHL schedule. Shows games played/playable, per-category winners, and a
  projected result.
- **Plan streaming week** — Helps plan streamer pickups for a selected
  matchup: a per-day roster grid with game markers and open active seats
  (optionally with your designated streamers dropped), a per-lineup-slot
  breakdown of the open seats, and NHL teams ranked by how many of the open
  days their schedule covers. Shows your used/allowed weekly adds. The first
  two days of the next matchup appear as informational columns. Elapsed
  days are excluded (dimmed); for finished weeks the tool offers to simulate
  the week as ongoing. Optionally ranks skater free agents by how many of
  the open days they would actually fill a lineup seat, with blended
  per-game category rates (see below) alongside (injured players are flagged
  DTD/OUT/IR).

### Luck

The round-robin table tells you how strong a team really was; the actual
record also depends on who the schedule happened to serve up. `Luck` is the
difference between actual and expected matchup points:

```
xPts = rr points / (teams − 1)
Luck = Pts − xPts
```

Each week a team earns actual points from its real matchup (2 for a win,
1 for a tie) and round-robin points from its `teams − 1` hypothetical
matchups; dividing the latter by `teams − 1` gives `xPts`, the points an
average schedule would have produced. Positive luck means the team got easier
opponents than average (its record flatters its strength), negative means
it ran into a tough schedule. Luck sums to zero across the league each week.

### Stat blending

Predictions build on per-game rates. For each player and category, the
current-season rate is blended linearly with ESPN's preseason projection,
weighted by how much of the season has elapsed:

```
rate = w · season per-game rate + (1 − w) · projected per-game rate
w    = elapsed scoring periods / season length
```

Early in the season the projection dominates (little evidence yet); as the
season progresses, the actual production takes over — at `w = 1` the
projection is ignored entirely. If one side is missing (e.g. a player with no
games yet, or no preseason projection), the other is used alone. Games played
come from `GP` for skaters and `GS` for goalies. Ratio categories (GAA, SV%)
are blended the same way but as ratios rather than per-game counts, and when
aggregated over a week they are averaged weighted by goalie games instead of
summed.

### Contestedness

The `(contested)` footer row of the category strength profile measures how
up-for-grabs a category is league-wide:

```
contested = 1 − std(win rates) / 0.5
```

Each category's win-rate column averages 0.5 by construction, so its standard
deviation says how spread out the teams are: everyone near 0.5 (std ≈ 0,
contested ≈ 1) means full parity — small roster moves can swing the category;
a wide spread (std → 0.5, contested → 0) means a few teams structurally own
it and chasing it is expensive.

## Tests

```bash
.venv/bin/pytest
```

## Repo overview

```
config.yaml                  # leagues and scoring categories (committed)
secrets.example.yaml         # template for secrets.yaml (ESPN cookies, gitignored)
pyproject.toml               # package metadata, dependencies, CLI entrypoint
src/fantasy_nhl/
  cli.py                     # interactive session: league picker + tool menu
  config.py                  # YAML loading into LeagueConfig/Category dataclasses
  espn_data.py               # ESPN API access: scores, rosters, NHL schedule, settings
  analysis.py                # pure logic: round-robin tables, predictions, lineup seats
  display.py                 # rich rendering: tables, color gradients
  tools.py                   # CLI tools and the TOOLS registry
tests/                       # pytest suite for the pure analysis logic
```

## Contributing

- Install with dev dependencies: `pip install -e ".[dev]"` (see Setup).
- **Adding a tool:** write a function in `tools.py` taking a `LeagueData`
  argument and register it in the `TOOLS` list — it appears in the CLI menu
  automatically. Keep computation in `analysis.py` (pure functions, no API
  calls), data fetching in `espn_data.py`, and render tables via
  `display.print_df` (per-cell styling through the `styles` mapping).
- **Adding a league:** append an entry under `leagues:` in `config.yaml` and
  a matching credentials entry in `secrets.yaml`.
  The category list must match what the league actually scores on ESPN;
  mark lower-is-better categories with `inverted: true`.
- Run `pytest` before committing. New analysis logic should come with tests;
  the ESPN layer is currently untested (requires live credentials).
