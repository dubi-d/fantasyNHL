"""Interactive CLI entrypoint."""
from .config import LeagueConfig, load_config
from .espn_data import fetch_league_data
from .tools import TOOLS


def _choose_league(leagues: list[LeagueConfig]) -> LeagueConfig:
    if len(leagues) == 1:
        return leagues[0]

    print("\nAvailable leagues:")
    for i, league in enumerate(leagues, start=1):
        print(f"  {i}. {league.name} ({league.year})")
    while True:
        choice = input(f"Select league [1-{len(leagues)}]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(leagues):
            return leagues[int(choice) - 1]
        print("Invalid selection.")


def main() -> None:
    leagues = load_config()
    league_config = _choose_league(leagues)

    print(f"\nFetching data for '{league_config.name}'...")
    data = fetch_league_data(league_config)
    print(f"Loaded {data.current_week - 1} completed weeks, "
          f"{len(data.team_names)} teams.")

    while True:
        print("\nTools:")
        for i, (label, _) in enumerate(TOOLS, start=1):
            print(f"  {i}. {label}")
        print("  q. Quit")

        choice = input(f"Select tool [1-{len(TOOLS)}, q]: ").strip().lower()
        if choice == "q":
            break
        if choice.isdigit() and 1 <= int(choice) <= len(TOOLS):
            TOOLS[int(choice) - 1][1](data)
        else:
            print("Invalid selection.")


if __name__ == "__main__":
    main()
