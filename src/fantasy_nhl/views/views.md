# views

What each tool shows, independent of where it is shown. A builder turns
league data and the user's choices into a `View`: an ordered list of
tables, notes, text and figures. The terminal app and the web backend
render the same views, which is why both always show the same thing.

## Boundaries

- A builder never fetches, prompts, prints or saves. Whatever it needs
  (the league, fetched data, the choices, the `StatBasis`) is passed in.
- Imports `analysis` and `config` only: nothing of the ESPN layer, the
  front ends,
  `plots`, `rich`, `questionary` or `matplotlib`. The types of the ESPN
  layer (`LeagueData`, `PreviewData`, ...) are imported under
  `TYPE_CHECKING` for annotations. Checked by
  [tests/test_layering.py](../../../tests/test_layering.py).
- No styles: a cell says *what* it is (a tone), each front end decides how
  that looks.

## Layout

| File | Holds |
| --- | --- |
| [model.py](model.py) | The view model: `View`, the block types, tones and their helpers, `cell_texts` |
| [common.py](common.py) | Shared by several views: labels and abbreviations, `player_view`, stat-basis titles, `completed_matchups`, `week_label` |
| [weekly.py](weekly.py) | Weekly scores and weekly awards |
| [standings.py](standings.py) | Accumulated scores, luck ranking, power rankings, category strength profile |
| [preview.py](preview.py) | Matchup preview |
| [streaming.py](streaming.py) | Streaming planner and the free-agent candidates |
| [schedule.py](schedule.py) | NHL schedule outlook and the calibration curve |
| [review.py](review.py) | `ReviewContext`: the valued player pool the next three build on |
| [players.py](players.py) | Category leaderboard and player comparison |
| [rosters.py](rosters.py) | Roster origins, category outlook, pickups and trades, team roster, drop candidates |
| [draft.py](draft.py) | Draft grades, hits and busts, a team's picks |

## The view model

A `View` holds `blocks` in display order:

- **`TableView`**: `frame` holds the values as displayed (already
  rounded), with the index as row label (a rank, or blank). `tones` is a
  frame of the same rows with a tone per cell for the columns that have
  one. `footer` rows go below the body, `muted` columns get a dimmed
  header, and `key` names a table a front end treats specially (the three
  planner tables).
- **`Note`**: text in spans, each optionally toned, with a level (plain,
  info, warning, alert, heading).
- **`TextBlock`**: text to show verbatim, for copying.
- **`FigureBlock`**: `kind` and `inputs` name the function
  `plots.<kind>_figure(**inputs)` in [plots.py](../plots.py) that draws
  it; `inputs` always has a `title`. Nothing is drawn while building.

A **tone** is `None`, a number from -1 (bad) to +1 (good) for gradients
(`diverging(value, scale)`, `heat(rate)`), or space-separated tags (`GOOD`,
`BAD`, `EVEN`, `WARN`, `DANGER`, `BENCH`, `MUTED`, `STRONG`).
`column_tones(frame, {column: rule})` builds the tone frame.

`cell_texts(frame)` is the one place that turns values into display text;
both front ends use it, so a number reads the same in the terminal and in
the browser.

`View.meta` is not filled by builders. The web backend puts what a page's
form needs there (see [api.md](../api/api.md)).

## Choices live here too

What the user can choose, and whether a choice is valid, is the same in
both front ends, so that logic sits next to the builders and not in a
front end: `select_schedule`, `schedule_scores` and `lead_choices` for the
schedule scopes and sort columns, `leader_sorts`, `cell_choices`,
`player_labels` and `check_pick` for the player views, `streaming_context`
for the planner, `has_players` for the review.

## Extending

- A new view is a function `build_<name>(...) -> View` in the module of
  its tool. Compute in `analysis`, shape and label here.
- Round and format in the builder; put the legend of a table in a `Note`
  after it.
- Views that rate players take the `StatBasis` and name it in their title
  with `with_basis`.
- Wire it into both front ends: see [cli.md](../cli/cli.md) and
  [api.md](../api/api.md), or the end-to-end steps in
  [docs/contributing.md](../../../docs/contributing.md).

## Gotchas

- Players are told apart by identity or id, never by name: namesakes
  exist (also on one NHL team).
- Row labels can repeat (the planner grid uses blank labels), so tones are
  matched to rows by position.
- A builder returns a fresh `View` on every call; front ends may add
  blocks to it.

## Tests

The golden transcripts run every builder through the terminal app, and
the API tests compare the served tables with those transcripts (see
[tests.md](../../../tests/tests.md)).
[tests/test_views_model.py](../../../tests/test_views_model.py) covers
tones and cell texts.
