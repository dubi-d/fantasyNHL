# cli

The terminal front end: arrow-key menus, wizard-style tools and tables
rendered with `rich`. It asks, fetches and renders; what is shown comes
from [views](../views/views.md).

## Boundaries

- May import `views`, `analysis`, `sources`, `config` and `plots`.
- Must not import the web backend (`api`, `fastapi`). Checked by
  [tests/test_layering.py](../../../tests/test_layering.py).
- The only layer that uses `rich` and `questionary`.

## Layout

| File | Holds |
| --- | --- |
| [app.py](app.py) | The entry point `main`, the league picker, the menu (`run_menu`) and the wizard runner (`run_tool`) |
| [prompts.py](prompts.py) | The prompt primitives: `ask`, the steps `Ask` and `Do`, the `BACK` sentinel |
| [display.py](display.py) | Rendering: `print_df` for tables, tones to `rich` styles, notes to markup |
| [tools.py](tools.py) | The tools themselves and the `TOOLS` menu tree |

## The menu

`TOOLS` is a nested list of `(label, value)` pairs. A list value is a
submenu, anything else a tool. A label can be a function of the
`LeagueData` instead of a string; it is read again whenever the menu is
shown (the *Player stats* entry shows its current value this way). ESC
goes up one level, and at the root the menu also offers Quit.

## Tools are wizards

A tool takes the `LeagueData`. Without prompts it is a plain function
that shows a view. With prompts it is a generator that yields steps and
receives their results:

```python
def my_tool(data):
    week = yield Ask(lambda: ask(questionary.select(...)))   # a prompt
    fetched = yield Do(lambda: fetch_something(data, week))  # a side effect
    yield Do(lambda: _show(data, build_something(data, fetched)))
```

`run_tool` keeps the history of results. When the user presses ESC at a
prompt, it drops that prompt and everything after it, starts the generator
again and replays the history into it. So:

- Results of `Do` steps before the changed prompt are reused: nothing is
  fetched or printed twice.
- Steps after it run again with the new answer.
- ESC at the first prompt returns to the menu. A tool that finishes
  starts over at its first prompt; a tool that never asked returns to the
  menu.

For this to work, the code between two `yield`s must have no side
effects: every fetch, every print and every saved figure belongs in a
`Do`.

## Prompts

- Always go through `ask(question)`. It binds ESC to `BACK` and lets
  Ctrl-C propagate as `KeyboardInterrupt` to `main`, which quits. Never
  call `.ask()` on a question inside a tool.
- `BACK` is its own object, not `None`: `questionary` swallows a choice
  whose value is `None`. For the same reason "no selection" choices use a
  sentinel such as `_SKIP` or `0`.
- `BACK` is truthy, so never write `ask(...) or default`.
- A prompt that offers players passes the player as the choice's value
  and his name as the title, so namesakes stay apart.

## Rendering

`_show(data, view)` in `tools.py` renders a view block by block: tables
through `print_df` with the tones mapped by `tone_style`, notes through
`note_markup`, text verbatim, and figures by drawing them with
[plots.py](../plots.py) and saving the PNG under `plots/`.

Two things are terminal-only and stay in `tools.py`: the planner pads its
three tables so that their day columns line up, and the free-agent
candidates are shown in pages.

## Extending

- Write the builder in `views`, then the tool here, and register it in
  `TOOLS`. A tool that rates players builds its `StatBasis` with
  `_stat_basis(data, fraction)`, which applies the *Player stats* setting.
- Add a scripted case to
  [tests/test_golden.py](../../../tests/test_golden.py).
- The same view needs an endpoint and a page for the web app: see
  [docs/contributing.md](../../../docs/contributing.md).

## Tests

- [tests/test_cli.py](../../../tests/test_cli.py): the wizard runner and
  the menu, with scripted fake prompts.
- [tests/test_prompts.py](../../../tests/test_prompts.py): ESC and Ctrl-C
  against real `questionary` prompts.
- [tests/test_tools.py](../../../tests/test_tools.py): planner rendering
  (colors, alignment) and wizard regressions.
- The golden transcripts drive every tool through the real menu (see
  [tests.md](../../../tests/tests.md)).
