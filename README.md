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
