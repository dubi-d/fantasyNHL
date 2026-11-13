# fantasyNHL

My repo for playing around with stats in my fantasy hockey league.
Uses [cwendt94/espn-api](https://github.com/cwendt94/espn-api).

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

The `[dev]` extra adds the development dependencies (pytest and the web
backend) so the test suite runs out of the box; for just using the CLI,
`pip install -e .` is enough, for the web app without tests
`pip install -e ".[web]"`.

## Configuration

Leagues and their scoring categories live in [config.yaml](config.yaml)
(committed). ESPN credentials (SWID / espn_s2 cookies) live in `secrets.yaml`
(gitignored), keyed by league name — copy
[secrets.example.yaml](secrets.example.yaml) to `secrets.yaml` and fill in
your cookies. Add or replace leagues as entries under `leagues:` plus a matching
entry in `secrets.yaml`. The optional `default_league:` names the league to
start on: the web app opens on it and the terminal menu preselects it.
Schedule-scoring calibrations are stored in
`calibration.yaml`, written by the calibrate option of the schedule outlook
tool — don't edit it by hand.

## Usage

```bash
.venv/bin/fantasy-nhl
```

Starts an interactive session: pick a league and tools from arrow-key menus.
League data is fetched once per session and reused.

```
Select tool
├── Weekly
│   ├── Show weekly scores
│   └── Generate weekly awards
├── Season standings
│   ├── Show accumulated scores
│   ├── Show luck ranking
│   ├── Show power rankings over time
│   └── Show category strength profile
├── Roster planning
│   ├── Show matchup preview
│   ├── Plan streaming week
│   └── Show NHL schedule outlook
├── Players, rosters & draft
├── Player stats: Blended (season + projection)
└── Quit
```

**Player stats** is a setting, not a tool: it decides which player stats
every `Score`, per-game rate and prediction is built from — *Blended*
(season stats mixed with ESPN's preseason projection, the default) or *This
season only* (no projection anywhere). The menu entry shows the current
value; it applies to all tools for the rest of the session and every
affected table names it in its title. See
[Player stats](docs/methodology.md#player-stats).

After a tool finishes it returns to its own first prompt, so you can re-run
it with different inputs right away. **ESC** goes back one step — the
previous prompt within a tool, or up one menu level (ESC at the top menu
quits); **Ctrl-C** quits immediately from anywhere. Stepping back doesn't
repeat fetches or tables already shown; only the steps after the changed
answer re-run.

## Web app

The same tools in the browser: a local FastAPI backend serving every view
as JSON and a React/TypeScript frontend rendering them, with the terminal's
prompts as form controls. It runs from a source checkout (the frontend is
built there, an installed wheel does not contain it) and needs Node.js
20.19+ or 22.12+ for the build.

```bash
cd web && npm ci && npm run build && cd ..   # once, and after frontend changes
.venv/bin/fantasy-nhl-web                    # http://127.0.0.1:8000
```

Run it from the repository root (it reads `config.yaml` and `secrets.yaml`
there). The sidebar mirrors the menu above; the league, the **Player stats**
setting and *Reload from ESPN* sit on top, with the time the league was
read ("as of"). A new browser tab opens on the `default_league`; without a
built frontend the server says how to build it.

How fresh the data is: the league itself (standings, rosters, current
matchup) is read from ESPN again once it is 15 minutes old, everything
fetched for a page (preview, lineups, free agents, ...) after 5 minutes,
and the browser asks the server again when a page it shows is older than
5 minutes. *Reload from ESPN* drops all of it at once - use it after
roster moves.

The address holds the league, the page and its choices
(`#/<league>/streaming?week=5&team=0&streamers=...`), so pages can be
bookmarked, reloaded and stepped through with back and forward. The
server listens on `127.0.0.1` only, answers no other host name, and never
sends the ESPN cookies to the browser (nor writes them to its log).

For working on the frontend, run the two parts separately:

```bash
.venv/bin/fantasy-nhl-web            # backend with your leagues, or:
.venv/bin/python tests/fake_server.py  # backend on the synthetic test league
cd web && npm run dev                # frontend with hot reload, http://127.0.0.1:5173
```

`tests/fake_server.py` takes a scenario of `tests/support.py` as argument
(`finished`, `opening_day`, `pre_draft`, ...). The API is described at
`http://127.0.0.1:8000/api/docs` and, as committed schema, in
`web/openapi.json`, from which the frontend's types are generated. After
changing the API:

```bash
UPDATE_OPENAPI=1 .venv/bin/pytest tests/test_api.py -k schema   # web/openapi.json
cd web && npm run types                                         # web/src/schema.d.ts
```

Both files are checked by the tests (`pytest`, `npm test`); `npm test` also
runs the frontend's component tests against scripted server answers.

## Tests

```bash
.venv/bin/pytest
```

`tests/test_golden.py` runs every tool through the real menu on a synthetic
league and compares the whole terminal session (output with colors, prompts,
fetch calls, figure inputs) with the transcripts in `tests/golden/`. After an
intended change to what a tool shows, regenerate them with
`UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_golden.py` and review the diff.

## Documentation

- [docs/tools.md](docs/tools.md): what each tool shows.
- [docs/methodology.md](docs/methodology.md): the definitions behind the
  numbers (luck, stat blending, schedule scoring, player value, ...).
- [docs/architecture.md](docs/architecture.md): how the code is laid out.
- [docs/contributing.md](docs/contributing.md): adding a tool or a league.
- [docs/draft-guide.md](docs/draft-guide.md): draft strategy for a
  daily-lineup head-to-head categories league.

