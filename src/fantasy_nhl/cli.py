"""Interactive CLI entrypoint."""
import questionary

from .config import LeagueConfig, load_config
from .display import console
from .espn_data import fetch_league_data
from .tools import TOOLS


def _choose_league(leagues: list[LeagueConfig]) -> LeagueConfig | None:
    if len(leagues) == 1:
        return leagues[0]

    return questionary.select(
        "Select league:",
        choices=[questionary.Choice(f"{league.name} ({league.year})", value=league)
                 for league in leagues],
    ).ask()


def main() -> None:
    leagues = load_config()
    league_config = _choose_league(leagues)
    if league_config is None:  # Ctrl-C
        return

    with console.status(f"Fetching data for '{league_config.name}'..."):
        data = fetch_league_data(league_config)
    console.print(f"Loaded [bold]{data.current_week - 1}[/] completed weeks, "
                  f"[bold]{len(data.team_names)}[/] teams.")

    while True:
        choice = questionary.select(
            "Select tool:",
            choices=[questionary.Choice(label, value=tool) for label, tool in TOOLS]
                    + [questionary.Choice("Quit", value=None, shortcut_key="q")],
            use_shortcuts=True,
        ).ask()
        if choice is None:  # Quit or Ctrl-C
            break
        choice(data)


if __name__ == "__main__":
    main()
