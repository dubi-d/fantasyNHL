"""Prompt primitives for the wizard-style tools: ESC goes back one step,
Ctrl-C quits (KeyboardInterrupt propagates to the entry point)."""
from dataclasses import dataclass
from typing import Any, Callable

import questionary
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings

BACK = object()  # ESC; never None (questionary swallows None choice values)


@dataclass(frozen=True)
class Ask:
    """A wizard prompt step; ``run`` returns the answer or BACK."""
    run: Callable[[], Any]


@dataclass(frozen=True)
class Do:
    """A wizard side-effect step (fetch, render, print); its result is
    memoized so going back and forward again does not repeat it."""
    run: Callable[[], Any]


def ask(question: questionary.Question) -> Any:
    """Ask with ESC bound to BACK; Ctrl-C raises KeyboardInterrupt."""
    kb = KeyBindings()

    @kb.add("escape", eager=True)
    def _back(event) -> None:
        event.app.exit(result=BACK)

    app = question.application
    # must happen before run(): prompt_toolkit merges app.key_bindings once
    app.key_bindings = merge_key_bindings(
        [b for b in (app.key_bindings, kb) if b is not None])
    app.ttimeoutlen = 0.1  # lone ESC otherwise waits ~0.5s for a sequence
    return question.unsafe_ask()
