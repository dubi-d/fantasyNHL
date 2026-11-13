# tests

The Python test suite. It runs offline: nothing in it asks ESPN. The
frontend's tests live in `web/src` and are described in
[web.md](../web/web.md).

```bash
.venv/bin/pytest                 # everything
.venv/bin/pytest -W error        # as it should pass: warnings are errors
.venv/bin/python -m pyflakes src/fantasy_nhl tests
```

## Layout

| File | Tests |
| --- | --- |
| [support.py](support.py) | Not a test: the synthetic league, its scenarios, and helpers to find and patch package names |
| [fake_server.py](fake_server.py) | Not a test: the web backend on the synthetic league, for frontend work |
| [test_analysis.py](test_analysis.py) | The functions of `analysis`, one class per function |
| [test_config.py](test_config.py) | Loading `config.yaml` and `secrets.yaml`, the default league, storing calibrations |
| [test_espn_data.py](test_espn_data.py) | The calendar parsing of the ESPN layer, with ESPN-shaped data |
| [test_plots.py](test_plots.py) | The player figures render to PNG |
| [test_views_model.py](test_views_model.py) | Tones, their terminal styles, cell texts |
| [test_prompts.py](test_prompts.py) | ESC and Ctrl-C against real `questionary` prompts |
| [test_cli.py](test_cli.py) | The wizard runner and the menu |
| [test_tools.py](test_tools.py) | Planner rendering in the terminal and wizard regressions |
| [test_golden.py](test_golden.py) | Every tool through the real menu, compared with the transcripts in `golden/` |
| [test_api.py](test_api.py) | The web backend on the synthetic league |
| [test_layering.py](test_layering.py) | The import rules between the layers |

## The synthetic league

`FakeLeague` in `support.py` is a small, deterministic league (four
teams, twenty NHL teams, eight matchups of which two are playoffs) with
data shaped like ESPN's. Its methods are named like the fetchers they
replace (`fetch_preview_data`, `fetch_roster_review`, ...; the list is
`FakeLeague.FETCHERS`), so a test patches each fetcher with the method of
the same name.

It and its scenarios contain the awkward cases on purpose: namesakes, a
player without a projection, a player without an id, an empty roster, IR
players, a category tie, an unlimited add budget.

The states the tests look at are named scenarios (`SCENARIOS`):
`midseason`, `finished`, `opening_day`, `preseason`, `pre_draft`,
`undrafted`. Add a scenario there instead of constructing a `FakeLeague`
with the same arguments in several tests; the fake server takes the same
names.

`lookup(name)` returns a package object wherever it is defined, and
`patch_everywhere(monkeypatch, name, value)` replaces it in every module
that imported it. Tests written with them keep working when code moves
between modules.

## Golden transcripts

`test_golden.py` runs the real menu with scripted answers on a scenario
and records the whole session: the output with its colors, every prompt
with its choices, every fetch, the inputs of every figure. The result
must equal `golden/<case>.txt` byte for byte.

- A case is `(scenario, answers)` in `CASES`. Answers are choice titles,
  `BACK` for ESC, a list for checkboxes, `Reject("text")` for input the
  validator must refuse. A script that runs out ends the session.
- Escape codes are written as `␛`, the spinner as `[status]`, the date is
  fixed, so the transcripts are stable.
- They depend on the installed `rich` version.

**Regenerate only for an intended change**, and only the cases it
affects:

```bash
UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_golden.py -k "planner or schedule"
git diff tests/golden      # read it: every changed line must be explained by the change
```

A transcript that changes without an intended change in what the tool
shows is a regression; fix the code, not the file.

## What the API tests rely on

`test_api.py` serves the synthetic league through the real app and checks,
among other things, that the tables of an endpoint equal the tables of
the terminal transcript for the same choices. So a view only needs to be
right once. It also holds the check of `web/openapi.json`; after an
intended API change regenerate it as described in
[api.md](../src/fantasy_nhl/api/api.md).

## Conventions

- New `analysis` logic comes with unit tests; a new tool with a golden
  case; a new endpoint with an entry in `VIEWS` and `INVALID`.
- A bug fix comes with a test that fails without it.
- Tests that need the ESPN layer patch the fetchers; none may open a
  connection.
- `pytest -W error` and `pyflakes` must stay clean.

## Manual checks

`fake_server.py [scenario]` serves the built frontend on the synthetic
league at `http://127.0.0.1:8000`, without ESPN and without touching
`calibration.yaml`. A check against real leagues is manual: start
`.venv/bin/fantasy-nhl-web`.
