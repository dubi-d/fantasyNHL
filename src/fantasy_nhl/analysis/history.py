"""One player's seasons in a history of NHL season stats (a table with a
row per player and season): his derived stats, per-game rates and average."""
import pandas as pd

# the games a count is divided by; never divided themselves
GAMES = ("GP", "GS")
# what a rate is a rate of, when it is not games played
_RATE_OF = {"GAA": "TOI", "SV%": "SA", "shootingPct": "SOG"}
_SHORT = {"points": "P", "penaltyMinutes": "PIM", "plusMinus": "+/-"}


def season_name(season: int) -> str:
    """An NHL season id as it is written (20252026 -> '2025-26')."""
    return f"{season // 10000}-{season % 100:02d}"


def is_rate(column: str) -> bool:
    """Whether a stat is a rate or ratio (anything else adds up)."""
    return (column in _RATE_OF or column == "TOI/GP"
            or column.endswith(("Per60", "PerGame", "Pct")))


def _rate_of(column: str) -> str:
    return _RATE_OF.get(column, "TOI" if column.endswith("Per60") else "GP")


def _stat(frame: pd.DataFrame, column: str) -> pd.Series:
    return (frame[column] if column in frame
            else pd.Series(float("nan"), index=frame.index))


def player_seasons(history: pd.DataFrame, player_id: int) -> pd.DataFrame:
    """The player's seasons, oldest first, by season id. P, PIM and +/-
    are the NHL's points, penaltyMinutes and plusMinus; added are STP
    (PPP + SHP), TOI (seconds on ice) and TOI/GP (seconds per game)."""
    seasons = (history[history["player_id"] == player_id]
               .drop(columns="player_id").sort_values("season")
               .set_index("season").rename(columns=_SHORT))
    seasons["STP"] = seasons["PPP"] + seasons["SHP"]
    # the NHL gives the total for goalies and the time per game for skaters
    seasons["TOI"] = _stat(seasons, "timeOnIce").fillna(
        _stat(seasons, "timeOnIcePerGame") * seasons["GP"])
    seasons["TOI/GP"] = seasons["TOI"] / seasons["GP"]
    return seasons.drop(columns=["timeOnIce", "timeOnIcePerGame"],
                        errors="ignore")


def per_game(seasons: pd.DataFrame) -> pd.DataFrame:
    """The seasons with every count divided by the games played; the
    games themselves and the rates stay."""
    rates = seasons.copy()
    counts = [column for column in seasons.select_dtypes("number")
              if not is_rate(column) and column not in GAMES]
    rates[counts] = seasons[counts].div(seasons["GP"], axis=0)
    return rates


def career_average(seasons: pd.DataFrame, rate: bool = False) -> pd.Series:
    """The player over all the given seasons, weighted by games: a count
    as its mean per season, or per game played with ``rate``; the games as
    their mean per season; a rate as what it is over all seasons together
    (the seasons' rates weighted by games, by ice time for GAA and per-60
    rates, by shots for SV% and shootingPct). A season without a value
    does not count for that stat."""
    average = {}
    for column, values in seasons.select_dtypes("number").items():
        known = values.notna()
        if is_rate(column):
            weights = seasons[_rate_of(column)]
            known &= weights.notna()
            total = weights[known].sum()
            average[column] = ((values[known] * weights[known]).sum() / total
                               if total else float("nan"))
        elif rate and column not in GAMES:
            games = seasons.loc[known, "GP"].sum()
            average[column] = (values[known].sum() / games if games
                               else float("nan"))
        else:
            average[column] = values.mean()
    return pd.Series(average, dtype=float)
