"""Interactive CLI entrypoint."""
import inspect
from typing import Any, Callable

import questionary

from .config import LeagueConfig, load_config
from .display import console
from .espn_data import fetch_league_data
from .prompts import BACK, Ask, Do, ask
from .tools import TOOLS


def _choose_league(leagues: list[LeagueConfig]) -> LeagueConfig | None:
    if len(leagues) == 1:
        return leagues[0]

    return questionary.select(
        "Select league:",
        choices=[questionary.Choice(f"{league.name} ({league.year})", value=league)
                 for league in leagues],
    ).ask()


def run_tool(data: Any, tool: Callable[[Any], Any]) -> None:
    """Run one tool until the user backs out of its first prompt.

    A plain function runs once. A generator function is a wizard yielding
    ``Ask`` (prompt) and ``Do`` (memoized side effect) steps and receiving
    each result via ``send``. BACK from a prompt discards that prompt and
    everything after it, then replays the remaining history into a fresh
    generator; BACK at the first prompt returns to the menu. A finished
    wizard starts over from its first prompt; a pass without any prompt
    (print-only tool, early exit) returns to the menu.
    """
    if not inspect.isgeneratorfunction(tool):
        tool(data)
        return
    history: list[tuple[bool, Any]] = []  # (is_prompt, result)
    while True:
        gen = tool(data)
        try:
            step = next(gen)
            for _, value in history:
                step = gen.send(value)
            while True:
                if isinstance(step, Do):
                    result = step.run()
                elif isinstance(step, Ask):
                    result = step.run()
                    if result is BACK:
                        break
                else:
                    raise TypeError(f"wizard yielded {step!r}, expected Ask/Do")
                history.append((isinstance(step, Ask), result))
                step = gen.send(result)
        except StopIteration:
            if not any(is_prompt for is_prompt, _ in history):
                return
            history = []
            continue
        # BACK: drop steps through the most recent prompt, then replay
        while history and not history[-1][0]:
            history.pop()
        if not history:
            return
        history.pop()


_QUIT = object()


def run_menu(data: Any, items: list[tuple[str, Any]],
             select: Callable[..., Any] = questionary.select) -> None:
    """Navigate a nested menu: ``items`` are (label, value) pairs where a
    list value is a submenu and anything else a tool. ESC pops one level
    (past the root exits); the root also offers Quit."""
    stack: list[tuple[str, list[tuple[str, Any]]]] = [("Select tool", items)]
    while stack:
        title, entries = stack[-1]
        choices = [questionary.Choice(label, value=(label, value))
                   for label, value in entries]
        if len(stack) == 1:
            choices.append(questionary.Choice("Quit", value=_QUIT,
                                              shortcut_key="q"))
        selection = ask(select(f"{title}:", choices=choices,
                               use_shortcuts=True))
        if selection is BACK:
            stack.pop()
        elif selection is _QUIT:
            return
        elif isinstance(selection[1], list):
            stack.append(selection)
        else:
            run_tool(data, selection[1])


def main() -> None:
    leagues = load_config()
    league_config = _choose_league(leagues)
    if league_config is None:  # Ctrl-C
        return

    with console.status(f"Fetching data for '{league_config.name}'..."):
        data = fetch_league_data(league_config)
    console.print(f"Loaded [bold]{data.current_week - 1}[/] completed weeks, "
                  f"[bold]{len(data.team_names)}[/] teams.")

    try:
        run_menu(data, TOOLS)
    except KeyboardInterrupt:
        console.print("Bye.")


if __name__ == "__main__":
    main()
