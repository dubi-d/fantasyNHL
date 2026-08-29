"""Matplotlib figure rendering (kept out of the rich-only display module)."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless backend; must be set before importing pyplot
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import MaxNLocator

# distinct marker per team so lines stay tellable apart where they cross
_MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*", "p", "h"]

# high-contrast qualitative palette (tab20 pairs near-identical hues at 14-16
# teams); ordered so teams sharing a marker (i, i+10) get far-apart hues
_COLORS = [
    "#e6194B", "#4363d8", "#3cb44b", "#f58231", "#911eb4",
    "#469990", "#f032e6", "#9A6324", "#808000", "#000000",
    "#000075", "#b8860b", "#800000", "#42d4f4", "#a9a9a9", "#ff69b4",
]


def _team_styles(teams: list[str]) -> dict[str, dict]:
    """Per-team plot kwargs: distinct color + marker, dashed beyond 10 teams."""
    return {team: {"color": _COLORS[i % len(_COLORS)],
                   "marker": _MARKERS[i % len(_MARKERS)],
                   "linestyle": "--" if i >= len(_MARKERS) else "-"}
            for i, team in enumerate(teams)}


def _spread(finals: pd.Series, min_gap: float) -> dict[str, float]:
    """Label y-positions near the given values, nudged apart top-down so
    they don't overlap."""
    positions = {}
    prev = None
    for team, value in finals.sort_values(ascending=False).items():
        y = float(value) if prev is None else min(float(value), prev - min_gap)
        positions[str(team)] = y
        prev = y
    return positions


def _team_labels(ax: plt.Axes, finals: pd.Series, min_gap: float,
                 styles: dict[str, dict]) -> None:
    last_week = finals.name
    for team, y in _spread(finals, min_gap).items():
        ax.text(last_week + 0.2, y, team, color=styles[team]["color"],
                va="center", fontsize=9, fontweight="bold")


def _setup_axes(ax: plt.Axes, subtitle: str, first_matchup: int) -> None:
    ax.set_title(subtitle, loc="left", fontsize=11)
    ax.set_xlabel("Matchup")
    ax.set_xlim(left=first_matchup)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.grid(alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)


def power_rankings_figure(form_ranks: pd.DataFrame, avg_points: pd.DataFrame,
                          window: int, title: str, path: Path) -> None:
    """Save a two-panel PNG: hot-streak rank bump chart on top, expected
    points per matchup below. Rows are teams, columns matchup numbers."""
    teams = [str(t) for t in form_ranks.index]
    weeks = list(form_ranks.columns)
    styles = _team_styles(teams)
    # accumulated xPts / matchups: RR Pts / (teams − 1) / matchup count
    expected = avg_points / (len(teams) - 1)

    width = max(9.0, 0.55 * len(weeks) + 4)
    fig, (ax_bump, ax_avg) = plt.subplots(
        2, 1, figsize=(width, 11), layout="constrained")
    fig.suptitle(title, fontsize=14, fontweight="bold")

    for team in teams:
        ax_bump.plot(weeks, form_ranks.loc[team], linewidth=2,
                     markersize=7, **styles[team])
        ax_avg.plot(weeks, expected.loc[team], linewidth=2,
                    markersize=7, **styles[team])

    _setup_axes(ax_bump, f"Power Rankings (strength over the last {window} matchups)",
                weeks[0])
    ax_bump.set_ylabel("Rank")
    ax_bump.set_yticks(range(1, len(teams) + 1))
    ax_bump.set_ylim(len(teams) + 0.5, 0.5)  # rank 1 on top
    # ranks grow downward on the inverted axis, so spread the negated values
    for team, y in _spread(-form_ranks[weeks[-1]], 1.0).items():
        ax_bump.text(weeks[-1] + 0.2, -y, team, color=styles[team]["color"],
                     va="center", fontsize=9, fontweight="bold")

    _setup_axes(ax_avg, "Season strength (expected points per matchup: 2 = win, 1 = tie)",
                weeks[0])
    ax_avg.set_ylabel("xPts per matchup")
    ax_avg.axhline(1.0, color="gray", linestyle="--", linewidth=1)
    ax_avg.annotate("league average", (weeks[0], 1.0),
                    xytext=(0, 4), textcoords="offset points",
                    color="gray", fontsize=8, style="italic")
    finals = expected[weeks[-1]]
    span = ax_avg.get_ylim()[1] - ax_avg.get_ylim()[0]
    _team_labels(ax_avg, finals, max(span * 0.045, 0.1), styles)

    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
