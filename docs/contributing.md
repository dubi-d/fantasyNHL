# Contributing

- Install with dev dependencies: `pip install -e ".[dev]"` (see
  [Setup](../README.md#setup)).
- **Adding a tool:** write a builder in `views/` that takes the
  `LeagueData`, anything already fetched and the user's choices, and returns
  a `View` (see `views/model.py`): tables as DataFrames with per-cell
  *tones* (`diverging`/`heat` intensities or tags like `GOOD`, `WARN`)
  instead of terminal styles, notes, verbatim text and figures. A builder
  never fetches, prompts or prints. Then write the tool in `cli/tools.py`,
  a function taking a `LeagueData`, and register it in the `TOOLS` tree (a
  nested list of `(label, tool)` or `(label, [children])` pairs — nest a
  list to add a submenu; a label can be a function of the `LeagueData` to
  show a current value). A tool without prompts is a plain function:
  `_show(data, build_x(data))`. A tool with prompts is a generator:
  `answer = yield Ask(lambda: ask(questionary.select(...)))` for each
  prompt and `result = yield Do(thunk)` for every side effect (fetch,
  render, save). The runner in `cli/app.py` memoizes `Do` results and
  replays answers when the user steps back with ESC, so keep the code
  between yields free of side effects and never call `.ask()` directly —
  `prompts.ask` is what makes ESC/Ctrl-C work. Keep computation in
  `analysis/` (pure functions, no API calls) and data fetching in
  `sources/espn/`. Anything that rates a player takes a `StatBasis` (the
  tool builds it with `_stat_basis` from the *Player stats* setting) and
  gets rates from `analysis.player_rate`. For the web app, add an endpoint
  in the matching module of `api/routes/` (a function decorated with
  `@view(path)` that fetches through the league session and returns the
  same `View`; give it a `meta=` model if the page needs more than the
  blocks), a case in `tests/test_api.py`, regenerate the schema and types
  (see *Web app*), and add a page in `web/src/pages/` that keeps its
  choices in the address (`usePageParams`).
- **Adding a league:** append an entry under `leagues:` in `config.yaml` and
  a matching credentials entry in `secrets.yaml`.
  The category list must match what the league actually scores on ESPN;
  mark lower-is-better categories with `inverted: true`.
- Run `pytest` before committing. New analysis logic should come with tests
  (`tests/test_analysis.py`), a new tool with a scripted case in
  `tests/test_golden.py`; the wizard runner and menu are covered by
  `tests/test_cli.py` with scripted fake prompts, the ESC/Ctrl-C prompt
  behavior by `tests/test_prompts.py` (real questionary prompts driven
  through a pipe), and config/calibration persistence by
  `tests/test_config.py`. Requests to ESPN are never made in tests: the
  parsing of its payloads is covered offline by `tests/test_espn_data.py`,
  the tools run on the fake fetchers of `tests/support.py`.
