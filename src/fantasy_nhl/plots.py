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


def _setup_grid_axes(ax: plt.Axes, table: pd.DataFrame, subtitle: str) -> None:
    ax.set_title(subtitle, loc="left", fontsize=11)
    ax.set_xticks(range(len(table.columns)),
                  [f"M{w}" for w in table.columns], fontsize=8)
    ax.set_yticks(range(len(table.index)), table.index, fontsize=8)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)


def _mark_playoffs(ax: plt.Axes, table: pd.DataFrame,
                   playoff_weeks: set[int]) -> None:
    po_idx = [j for j, w in enumerate(table.columns) if w in playoff_weeks]
    if not po_idx:
        return
    first = min(po_idx)
    ax.axvline(first - 0.5, color="crimson", linewidth=2)
    for j in po_idx:
        ax.get_xticklabels()[j].set_color("crimson")
        ax.get_xticklabels()[j].set_fontweight("bold")
    ax.text(first - 0.4, -0.9, "playoffs", color="crimson",
            fontsize=8, style="italic", ha="left")


def _schedule_panel(ax: plt.Axes, table: pd.DataFrame, subtitle: str,
                    cmap: str, playoff_weeks: set[int],
                    labels: pd.DataFrame | None = None) -> None:
    """Annotated teams-x-matchups heatmap with playoff columns marked."""
    values = table.to_numpy()
    ax.imshow(values, cmap=cmap, aspect="auto")
    _setup_grid_axes(ax, table, subtitle)
    mid = (values.min() + values.max()) / 2
    text = values if labels is None else labels.to_numpy()
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            ax.text(j, i, str(text[i, j]), ha="center", va="center",
                    fontsize=7,
                    color="white" if values[i, j] > mid else "black")
    _mark_playoffs(ax, table, playoff_weeks)


# off-night text gradient endpoints, dark enough to read on the light blues
_OFF_TEXT_LOW = (0.60, 0.13, 0.13)
_OFF_TEXT_HIGH = (0.05, 0.47, 0.05)


def schedule_heatmap_figure(games: pd.DataFrame, off: pd.DataFrame,
                            playoff_weeks: set[int], off_label: str,
                            title: str, path: Path) -> None:
    """Save a single-panel PNG showing games (off-night games) per matchup:
    background shades by games, the parenthesized number colors red-to-green
    by off-night count. Rows are NHL teams, columns matchup numbers."""
    width = max(9.0, 0.9 * len(games.columns) + 3)
    height = max(8.0, 0.42 * len(games.index) + 2)
    fig, ax = plt.subplots(figsize=(width, height), layout="constrained")
    fig.suptitle(title, fontsize=14, fontweight="bold")
    g = games.to_numpy()
    o = off.to_numpy()
    # widen vmax so the background stays light enough for the colored text
    g_span = max(int(g.max()) - int(g.min()), 1)
    ax.imshow(g, cmap="Greys", aspect="auto",
              vmin=g.min(), vmax=g.min() + 2.8 * g_span)
    _setup_grid_axes(ax, games,
                     f"Games (off-night games) per matchup ({off_label})")
    o_span = max(int(o.max()) - int(o.min()), 1)
    for i in range(g.shape[0]):
        for j in range(g.shape[1]):
            ax.text(j - 0.03, i, str(g[i, j]), ha="right", va="center",
                    fontsize=7, fontweight="bold", color="black")
            t = (o[i, j] - o.min()) / o_span
            color = tuple(lo + (hi - lo) * t for lo, hi
                          in zip(_OFF_TEXT_LOW, _OFF_TEXT_HIGH))
            ax.text(j + 0.03, i, f"({o[i, j]})", ha="left", va="center",
                    fontsize=7, fontweight="bold", color=color)
    _mark_playoffs(ax, games, playoff_weeks)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def schedule_combined_figure(games: pd.DataFrame, off: pd.DataFrame,
                             off_label: str, title: str, path: Path) -> None:
    """Save a single-panel PNG: cells show games (off-night games), colored
    by off-night count. Rows are NHL teams, columns matchup numbers."""
    labels = games.astype(str) + " (" + off.astype(str) + ")"
    width = max(9.0, 0.9 * len(games.columns) + 3)
    height = max(8.0, 0.42 * len(games.index) + 2)
    fig, ax = plt.subplots(figsize=(width, height), layout="constrained")
    fig.suptitle(title, fontsize=14, fontweight="bold")
    _schedule_panel(ax, off,
                    f"Games (off-night games) per matchup ({off_label})",
                    "Greens", set(), labels=labels)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
