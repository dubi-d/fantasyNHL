# fantasyNHL
My repo for playing around with stats in my fantasy hockey league.
Uses [cwendt94/espn-api](https://github.com/cwendt94/espn-api).

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Configuration

Leagues and their scoring categories live in [config.yaml](config.yaml)
(committed). ESPN credentials (SWID / espn_s2 cookies) live in `secrets.yaml`
(gitignored), keyed by league name — copy
[secrets.example.yaml](secrets.example.yaml) to `secrets.yaml` and fill in
your cookies. Add more leagues as entries under `leagues:` plus a matching
entry in `secrets.yaml`.

## Usage

```bash
.venv/bin/fantasy-nhl
```

Starts an interactive session: pick a league, then choose a tool from the menu
(weekly round-robin scores, accumulated standings). League data is fetched
once per session and reused.

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
  espn_data.py               # ESPN API access; fetches weekly category scores
  analysis.py                # pure logic: matchup results, round-robin tables
  tools.py                   # CLI tools and the TOOLS registry
tests/                       # pytest suite for the pure analysis logic
```

## Contributing

- Install with dev dependencies: `pip install -e ".[dev]"` (see Setup).
- **Adding a tool:** write a function in `tools.py` taking a `LeagueData`
  argument and register it in the `TOOLS` list — it appears in the CLI menu
  automatically. Keep computation in `analysis.py` (pure functions, no API
  calls) and data fetching in `espn_data.py`.
- **Adding a league:** append an entry under `leagues:` in `config.yaml` and
  a matching credentials entry in `secrets.yaml`.
  The category list must match what the league actually scores on ESPN;
  mark lower-is-better categories with `inverted: true`.
- Run `pytest` before committing. New analysis logic should come with tests;
  the ESPN layer is currently untested (requires live credentials).
