# Contributing

Install with the dev dependencies (`pip install -e ".[dev]"`, see
[Setup](../README.md#setup)) and read [architecture.md](architecture.md)
first: it says which layer does what. Each layer's own doc has the
details; the steps below link to them.

## Adding a tool

1. **Compute** in [analysis](../src/fantasy_nhl/analysis/analysis.md):
   pure functions, no ESPN access, with unit tests. Anything that rates a
   player takes a `StatBasis` and gets its rates from `player_rate`.
2. **Fetch**, if the tool needs data nothing fetches yet, in
   [sources/espn](../src/fantasy_nhl/sources/espn/espn.md).
3. **Build the view** in [views](../src/fantasy_nhl/views/views.md): a
   function that takes the `LeagueData`, what was fetched and the user's
   choices and returns a `View`. It never fetches, prompts or prints.
4. **Terminal:** write the tool in `cli/tools.py` and register it in the
   `TOOLS` tree. A tool with prompts is a generator of `Ask` and `Do`
   steps; see [cli.md](../src/fantasy_nhl/cli/cli.md) for the rules that
   make ESC work. Add a scripted case to `tests/test_golden.py`.
5. **Web:** add the endpoint, regenerate the schema and the types, and
   add the page; see [api.md](../src/fantasy_nhl/api/api.md) and
   [web.md](../web/web.md).
6. **Document:** describe the tool in [tools.md](tools.md), new
   definitions in [methodology.md](methodology.md), and new files in
   their folder's doc.

## Adding a league

Append an entry under `leagues:` in `config.yaml` and a matching
credentials entry in `secrets.yaml`. The category list must match what
the league actually scores on ESPN; mark lower-is-better categories with
`inverted: true`.

## Before committing

```bash
.venv/bin/pytest -W error
.venv/bin/python -m pyflakes src/fantasy_nhl tests
npm --prefix web test        # after frontend or API changes
```

What needs which test, how the golden transcripts work and when to
regenerate them is in [tests.md](../tests/tests.md). Requests to ESPN are
never made in tests.
