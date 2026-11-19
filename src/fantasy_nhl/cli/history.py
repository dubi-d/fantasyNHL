"""The `fantasy-nhl-history` command: finished NHL seasons as CSV files."""
import argparse
import sys
from datetime import date

from ..sources.nhl import (
    NhlStatsError,
    fetch_season_ends,
    fetch_season_stats,
    save_season_stats,
    season_label,
    season_path,
)


def _download(years: list[int], refresh: bool) -> None:
    ends = None
    for year in dict.fromkeys(years):
        label, path = season_label(year), season_path(year)
        if path.exists() and not refresh:
            print(f"{label}: already in {path} (--refresh downloads it again)")
            continue
        if ends is None:
            ends = fetch_season_ends()
        if year not in ends:
            raise NhlStatsError(f"The NHL has no season ending in {year}.")
        if date.today() <= ends[year]:
            raise NhlStatsError(
                f"The {label} regular season is not over (it ends on "
                f"{ends[year]:%Y-%m-%d}); its totals would be partial.")
        rows = fetch_season_stats(year)
        save_season_stats(year, rows)
        goalies = sum(row["position"] == "G" for row in rows)
        print(f"{label}: {len(rows) - goalies} skaters and {goalies} goalies "
              f"-> {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fantasy-nhl-history",
        description="Download the regular-season stats of every NHL player "
                    "for finished seasons, one CSV file per season under "
                    "data/nhl/ of the working directory.")
    parser.add_argument(
        "years", metavar="YEAR", type=int, nargs="+",
        help="the year a season ends in, as in config.yaml (2026 = 2025-26)")
    parser.add_argument(
        "--refresh", action="store_true",
        help="download a season again even if its file exists")
    args = parser.parse_args(argv)
    try:
        _download(args.years, args.refresh)
    except NhlStatsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0
