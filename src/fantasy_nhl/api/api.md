# api

The web backend: a local FastAPI app that serves every view as JSON, with
the terminal's prompts as query parameters, and the figures as PNG. The
frontend that renders it is in [web](../../../web/web.md).

## Boundaries

- May import `views`, `analysis`, `sources`, `config` and `plots`.
- Must not import the terminal front end or its libraries (`cli`, `rich`,
  `questionary`), nor `espn_api` directly. Checked by
  [tests/test_layering.py](../../../tests/test_layering.py).
- Needs the `web` extra (`fastapi`, `uvicorn`); nothing else in the
  package imports this layer.
- An endpoint fetches and calls a builder; it does not compute or format.

## Layout

| File | Holds |
| --- | --- |
| [app.py](app.py) | `create_app`: local-only middleware, the ESPN error handler, the static frontend (or a hint how to build it); `main` runs it on `127.0.0.1:8000` |
| [state.py](state.py) | `LeagueStore`, `LeagueEntry`, `LeagueSession`: loading, caching and reloading leagues |
| [serialize.py](serialize.py) | The response models and `serialize_view`: a `View` as JSON |
| [figures.py](figures.py) | Figures as PNG: content fingerprint and a small cache of rendered images |
| [routes/base.py](routes/base.py) | Shared by the route modules: league dependencies, the write guard, parameter checks, `view()` |
| [routes/league.py](routes/league.py) | The leagues, what the forms need to know about one, reload |
| [routes/standings.py](routes/standings.py) | Weekly scores and awards, season standings |
| [routes/planning.py](routes/planning.py) | Matchup preview, streaming planner, schedule outlook and calibration |
| [routes/review.py](routes/review.py) | Players, rosters and the draft |

## Leagues, sessions and caching

- `LeagueStore` holds one `LeagueEntry` per league of `config.yaml`. Its
  id is the league's name as a slug and appears in every address.
- A `LeagueSession` is **one load** of a league: the `LeagueData` snapshot,
  when it was read (`loaded_at`), and everything fetched or derived for
  it. `LeagueEntry.session()` loads the league on first use and again once
  the session is `SESSION_SECONDS` (15 minutes) old; `reload()` drops it.
- Within a session, `fetch(key, fn)` caches an ESPN fetch for
  `CACHE_SECONDS` (5 minutes), and `derived(key, source, fn)` keeps a
  value computed from a fetched object until that object is fetched anew.
- Because the cache belongs to the session, a request that started before
  a reload can never put old data into the new session.
- A session has a lock: `espn_api`'s client is not thread-safe, and
  FastAPI runs these endpoints in a thread pool. Building views happens
  outside the lock and only reads.
- A failed fetch becomes `UpstreamError`, answered as 502 with the
  exception type only. The log gets the type and the traceback frames but
  not the message, which can contain the ESPN cookies.

## Endpoints

Everything is under `/api`; the interactive description is at
`/api/docs`.

- A view endpoint is a function that returns a `View`, registered with
  `@view(path)` (each route module binds it to its router). That creates
  the JSON endpoint and `<path>/figures/<n>.png` for its figures.
- A view whose page needs more than the blocks declares a model:
  `@view(path, meta=PlanMeta)`. The builder's `View.meta` is validated
  into it and the response model becomes `PlanView`. Views without one
  have no `meta`.
- Parameters mirror the terminal's prompts. Teams are their row index,
  players their ESPN id, `stats` is `blended` or `season`. A parameter
  left out means the default (current matchup, latest completed matchup).
- A parameter that is wrong or does not apply is refused with 422 and a
  one-line reason (`invalid`, `in_range`, `team_row`); it is never
  silently ignored. "Nothing to show" (no completed matchup, not drafted)
  is not an error: the view is a single warning note.
- Reads are `GET` and change nothing. What changes state (reload, saving
  a calibration) is `POST`/`PUT` behind `local_write`.

## What the JSON looks like

`serialize_view` turns the blocks into `TableBlock`, `NoteBlock`,
`TextBlockModel` and `FigureBlockModel`:

- A column has a `key`, a `name`, a `type` (`number` or `text`), an
  alignment and whether its header is muted. A cell has the displayed
  `text`, the `value` behind it (the displayed number, not a more precise
  one) and its `tone`.
- A figure has its `kind`, `title`, the `url` of the PNG and `data`: the
  inputs it is drawn from, as tagged frames and series, for clients that
  want to draw it themselves.

## Figures

A figure's address ends in `?...&v=<fingerprint>`, where the fingerprint
is a hash of its inputs. Equal content has an equal address, so the
browser may keep the image for good (`immutable`); asked for without the
mark, it is revalidated by its `ETag`. A PNG is rendered once per fingerprint and the
last 32 are kept in memory. Rendering is serialized by a lock because
`pyplot` keeps global state, and never leaves a figure open.

## Local only

The server is for one user on his own machine and has no login. It
therefore:

- listens on `127.0.0.1` only;
- answers only to the host names `127.0.0.1` and `localhost`, so that a
  page of another site cannot reach it through DNS rebinding;
- accepts state changes only as JSON and without a foreign `Origin`, which
  a page of another site cannot send without permission;
- never sends the ESPN cookies to the browser or writes them to the log.

Do not bind it to another interface without adding authentication.

## The schema and the frontend's types

`web/openapi.json` is the committed API schema; the frontend's types in
`web/src/schema.d.ts` are generated from it. After changing an endpoint,
a parameter or a response model:

```bash
UPDATE_OPENAPI=1 .venv/bin/pytest tests/test_api.py -k schema   # web/openapi.json
npm --prefix web run types                                      # web/src/schema.d.ts
```

A test on each side fails when one of the two files is out of date.

## Extending

1. Add a function to the route module of its area, decorated with
   `@view(path)`, taking `session: Session` and its query parameters.
2. Whatever asks ESPN goes through
   `session.fetch(key, lambda: fetch_x(session.data, ...))`, so that it is
   cached, locked and its failures are handled. Return the builder's
   `View`.
3. Add its address to `VIEWS` (and wrong parameters to `INVALID`) in
   [tests/test_api.py](../../../tests/test_api.py), and compare its tables
   with the terminal transcript if it has one.
4. Regenerate the schema and the types, then add the page (see
   [web.md](../../../web/web.md)).

## Tests

[tests/test_api.py](../../../tests/test_api.py) runs the app on the
synthetic league: every view is served, its tables equal the terminal's,
wrong parameters are refused, sessions expire and reload cleanly, state
changes are guarded, failures leak nothing. See
[tests.md](../../../tests/tests.md).
