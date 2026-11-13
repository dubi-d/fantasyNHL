# Architecture

## Repo overview

```
config.yaml                  # leagues and scoring categories (committed)
secrets.example.yaml         # template for secrets.yaml (ESPN cookies, gitignored)
calibration.yaml             # stored schedule-scoring calibrations (auto-managed)
pyproject.toml               # package metadata, dependencies, CLI entrypoint
src/fantasy_nhl/
  config.py                  # YAML loading into LeagueConfig/Category dataclasses
  sources/espn/              # ESPN API access (public names re-exported by the package)
    league.py                #   the league session: weekly scores, results, fetch caches
    calendar.py              #   NHL schedule mapped onto ESPN's fantasy calendar
    players.py               #   rosters, saved lineups, free agents, player info
    preview.py, review.py, calibration.py   # the fetches behind those tools
  analysis/                  # pure logic (all names re-exported by the package)
    models.py                #   player/draft records, position groups
    rates.py, ranking.py     #   per-game rates and their blend; rank statistics
    standings.py, seats.py, schedule.py, preview.py
    draft.py, outlook.py, values.py, review.py
  plots.py                   # matplotlib figures (power rankings, schedule grids, player profiles)
  views/                     # what each tool shows, independent of the frontend
    model.py                 #   View = ordered blocks: tables with cell tones, notes, text, figures
    common.py                #   shared formatting: player tables, abbreviations, stat-basis labels
    weekly.py, standings.py, preview.py, streaming.py, schedule.py
    review.py                #   the valued player pool behind players.py, rosters.py, draft.py
  cli/                       # the terminal frontend
    app.py                   #   interactive session: league picker, menu tree, wizard runner
    prompts.py               #   prompt primitives: Ask/Do steps, ESC = back, Ctrl-C = quit
    display.py               #   rich rendering: tables, tone -> color mapping
    tools.py                 #   the tools (prompts, fetches, rendering of views) and the TOOLS menu tree
  api/                       # the web backend (FastAPI)
    state.py                 #   per league: its current load (session) with fetch cache, expiry, reload
    serialize.py             #   View -> JSON models (typed columns, figure data, per-view meta)
    figures.py               #   figures as PNG, rendered once per content
    routes/                  #   one endpoint per view, prompts as query parameters
      base.py                #     league dependencies, write guard, registration of views
      league.py, standings.py, planning.py, review.py
    app.py                   #   the app: local-only middleware, static frontend, entrypoint
web/                         # the web frontend (Vite, React, TypeScript)
  openapi.json               #   the API schema (generated, checked by the tests)
  src/schema.d.ts            #   its TypeScript types (generated)
  src/session.tsx, params.ts #   the league of the address; a page's choices in the address
  src/components/View.tsx    #   generic renderer of a served view (tables, notes, text, figures)
  src/pages/                 #   one page per tool: its form controls around the view
tests/                       # pytest suite; support.py = synthetic league and its scenarios, golden/ = transcripts
```

Imports point one way, checked by `tests/test_layering.py`: `analysis` knows
nothing of ESPN, views or the terminal; `views` build on `analysis` and import
neither `rich`, `questionary`, `matplotlib` nor the ESPN layer; `cli` and
`api` are the two frontends that fetch and render, and know nothing of each
other.

