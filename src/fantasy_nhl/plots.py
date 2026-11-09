"""Matplotlib figure rendering (kept out of the rich-only display module)."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless backend; must be set before importing pyplot
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import MaxNLocator

from .analysis import PEAK_CATS, SPEC_HIGH, SPEC_LOW, TIER_ELITE, TIER_SOLID

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


def _setup_grid_axes(ax: plt.Axes, table: pd.DataFrame, subtitle: str,
                     extra_cols: list[str] | None = None) -> None:
    ax.set_title(subtitle, loc="left", fontsize=11)
    labels = ([f"M{w}" for w in table.columns]
              + [c.replace(" ", "\n") for c in extra_cols or []])
    ax.set_xticks(range(len(labels)), labels, fontsize=8)
    ax.xaxis.tick_top()
    if extra_cols:  # blank room right of the grid for the score columns
        ax.set_xlim(-0.5, len(labels) - 0.5)
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
    # below the grid: the top edge belongs to the matchup labels now
    ax.text(first - 0.4, len(table.index), "playoffs", color="crimson",
            fontsize=8, style="italic", ha="left", va="center")


def _score_columns(ax: plt.Axes, scores: dict[str, pd.Series],
                   ncols: int) -> None:
    """Score values right of the grid, red-to-green per column."""
    for k, (name, series) in enumerate(scores.items()):
        vals = series.to_numpy(dtype=float)
        span = (vals.max() - vals.min()) or 1.0
        for i, v in enumerate(vals):
            t = (v - vals.min()) / span
            color = tuple(lo + (hi - lo) * t for lo, hi
                          in zip(_OFF_TEXT_LOW, _OFF_TEXT_HIGH))
            ax.text(ncols + k, i, f"{v:.2f}", ha="center", va="center",
                    fontsize=7, fontweight="bold", color=color)


def _schedule_panel(ax: plt.Axes, table: pd.DataFrame, subtitle: str,
                    cmap: str, playoff_weeks: set[int],
                    labels: pd.DataFrame | None = None,
                    scores: dict[str, pd.Series] | None = None) -> None:
    """Annotated teams-x-matchups heatmap with playoff columns marked."""
    values = table.to_numpy()
    ax.imshow(values, cmap=cmap, aspect="auto")
    _setup_grid_axes(ax, table, subtitle, extra_cols=list(scores or {}))
    mid = (values.min() + values.max()) / 2
    text = values if labels is None else labels.to_numpy()
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            ax.text(j, i, str(text[i, j]), ha="center", va="center",
                    fontsize=7,
                    color="white" if values[i, j] > mid else "black")
    _score_columns(ax, scores or {}, len(table.columns))
    _mark_playoffs(ax, table, playoff_weeks)


# off-night text gradient endpoints, dark enough to read on the light blues
_OFF_TEXT_LOW = (0.60, 0.13, 0.13)
_OFF_TEXT_HIGH = (0.05, 0.47, 0.05)


def schedule_heatmap_figure(games: pd.DataFrame, off: pd.DataFrame,
                            playoff_weeks: set[int], off_label: str,
                            title: str, path: Path,
                            scores: dict[str, pd.Series] | None = None,
                            ) -> None:
    """Save a single-panel PNG showing games (off-night games) per matchup:
    background shades by games, the parenthesized number colors red-to-green
    by off-night count. Rows are NHL teams, columns matchup numbers."""
    ncols = len(games.columns) + len(scores or {})
    width = max(9.0, 0.9 * ncols + 3)
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
                     f"Games (off-night games) per matchup ({off_label})",
                     extra_cols=list(scores or {}))
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
    _score_columns(ax, scores or {}, len(games.columns))
    _mark_playoffs(ax, games, playoff_weeks)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def category_radar_figure(pcts: pd.DataFrame, title: str, path: Path) -> None:
    """Save a radar PNG of category percentiles (0-100): one polygon per
    row (player label), one axis per column (category)."""
    cats = [str(c) for c in pcts.columns]
    angles = np.linspace(0, 2 * np.pi, len(cats), endpoint=False).tolist()
    styles = _team_styles([str(p) for p in pcts.index])
    fig, ax = plt.subplots(figsize=(8, 8), layout="constrained",
                           subplot_kw={"projection": "polar"})
    fig.suptitle(title, fontsize=14, fontweight="bold")
    for label, row in pcts.iterrows():
        values = row.fillna(0).to_list()
        style = styles[str(label)]
        ax.plot(angles + angles[:1], values + values[:1], linewidth=2,
                color=style["color"], marker=style["marker"], label=str(label))
        ax.fill(angles + angles[:1], values + values[:1],
                color=style["color"], alpha=0.12)
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_xticks(angles, cats, fontsize=11, fontweight="bold")
    ax.set_ylim(0, 100)
    ax.set_yticks([25, 50, 75, 100], ["25", "50", "75", "100"],
                  fontsize=8, color="gray")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.06),
              ncol=min(len(pcts.index), 4), frameon=False)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


_GROUP_COLORS = {"F": "#4363d8", "D": "#f58231", "G": "#3cb44b"}


def level_spec_figure(summary: pd.DataFrame, highlight: pd.Series,
                      title: str, path: Path) -> None:
    """Save a Level-vs-Spec scatter PNG: every summary row (category
    profile with Group/Level/Spec) as a grey dot, the highlight rows
    (index subset -> label) colored by group and labeled."""
    pool = summary.dropna(subset=["Level", "Spec"])
    shown = pool.loc[pool.index.intersection(highlight.index)]
    fig, ax = plt.subplots(figsize=(11, 8), layout="constrained")
    fig.suptitle(title, fontsize=14, fontweight="bold")
    ax.scatter(pool["Level"], pool["Spec"], s=12, color="lightgray",
               zorder=1)
    for group, members in shown.groupby("Group"):
        ax.scatter(members["Level"], members["Spec"], s=40, zorder=3,
                   color=_GROUP_COLORS.get(str(group), "black"),
                   edgecolor="black", linewidth=0.5, label=str(group))
    for pid, row in shown.iterrows():
        ax.annotate(str(highlight[pid]), (row["Level"], row["Spec"]),
                    xytext=(4, 3), textcoords="offset points", fontsize=7)
    top = max(100.0, float(pool["Spec"].max()) + 5) if len(pool) else 100.0
    for x in (TIER_SOLID, TIER_ELITE):
        ax.axvline(x, color="gray", linestyle="--", linewidth=1)
    for y in (SPEC_LOW, SPEC_HIGH):
        ax.axhline(y, color="gray", linestyle="--", linewidth=1)
    for name, x in (("Depth", TIER_SOLID / 2), ("Solid", (TIER_SOLID + TIER_ELITE) / 2),
                    ("Elite", (TIER_ELITE + 100) / 2)):
        ax.text(x, top - 1, name, ha="center", va="top", fontsize=11,
                color="gray", style="italic", fontweight="bold")
    for name, y, va in (("specialists", SPEC_HIGH + 1, "bottom"),
                        ("all-rounders", SPEC_LOW - 1, "top")):
        ax.text(1, y, name, ha="left", va=va, fontsize=10, color="gray",
                style="italic", fontweight="bold")
    ax.set_xlim(0, 101)
    ax.set_ylim(0, top)
    ax.set_xlabel("Level (Score percentile within the position group)")
    ax.set_ylabel(f"Spec (Peak − Breadth: best {PEAK_CATS} categories vs "
                  "the rest, percentile points)")
    ax.grid(alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)
    if len(shown):
        ax.legend(loc="lower left", frameon=False)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def schedule_combined_figure(games: pd.DataFrame, off: pd.DataFrame,
                             off_label: str, title: str, path: Path,
                             scores: dict[str, pd.Series] | None = None,
                             ) -> None:
    """Save a single-panel PNG: cells show games (off-night games), colored
    by off-night count. Rows are NHL teams, columns matchup numbers."""
    labels = games.astype(str) + " (" + off.astype(str) + ")"
    ncols = len(games.columns) + len(scores or {})
    width = max(9.0, 0.9 * ncols + 3)
    height = max(8.0, 0.42 * len(games.index) + 2)
    fig, ax = plt.subplots(figsize=(width, height), layout="constrained")
    fig.suptitle(title, fontsize=14, fontweight="bold")
    _schedule_panel(ax, off,
                    f"Games (off-night games) per matchup ({off_label})",
                    "Greens", set(), labels=labels, scores=scores)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
