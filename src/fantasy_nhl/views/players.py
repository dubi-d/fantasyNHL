"""Player views: the category leaderboard and the player comparison."""
import pandas as pd

from ..analysis import PEAK_CATS, RATIO_CATEGORIES, StatBasis
from .common import (
    NO_PROJECTION,
    PLAYER_TONES,
    SLOT_ABBREV,
    percentile_tone,
    player_view,
    score_tone,
    with_basis,
)
from .model import (
    INFO,
    WARNING,
    FigureBlock,
    TableView,
    View,
    column_tones,
    diverging,
    note,
)
from .review import ReviewContext

LEADERS_N = 30  # leaderboard rows (one team's roster: all)
COMPARE_MAX = 4  # players per comparison
GROUP_CHOICES = {"F": "Forwards", "D": "Defense", "FD": "Skaters (F + D)",
                 "G": "Goalies"}
CELL_CHOICES = {"pct": "Percentiles", "rate": "Per-game rates",
                "total": "Season totals"}


def leader_sorts(ctx: ReviewContext, group: str) -> list[str]:
    """What a leaderboard of that position group can be sorted by."""
    names = ctx.group_cats(group == "G")
    return ["Score"] + (["Spec"] if len(names) > PEAK_CATS else []) + [
        "Elite"] + names


def cell_choices(basis: StatBasis) -> dict[str, str]:
    """Leaderboard cell contents on offer (key -> label)."""
    # season totals only next to season stats, never next to blended ones
    return {key: label for key, label in CELL_CHOICES.items()
            if key != "total" or basis.season_only}


def _stat_text(cat: str, value: float, per_game: bool) -> str:
    """Season total / per-game rate as text (ratio categories as is)."""
    if pd.isna(value):
        return ""
    if cat == "SV%":
        return f"{value:.3f}"
    if cat in RATIO_CATEGORIES or per_game:
        return f"{value:.2f}"
    return f"{value:.0f}"


def _stat_column(cat: str, values: pd.Series, cells: str) -> pd.Series:
    """Numeric leaderboard cell column, rounded for display."""
    if cells == "pct":
        return values.round(0).astype("Int64")
    if cat == "SV%":
        return values.round(3)
    if cells == "rate" or cat in RATIO_CATEGORIES:
        return values.round(2)
    return values.round(0).astype("Int64")


def build_leaders(ctx: ReviewContext, scope: str, row: int | None,
                  group: str, sort: str, cells: str) -> View:
    """
    Category leaderboard with the level-vs-specialization map.

    :param scope: "all" (whole pool), "fa" (free agents) or "team"
    :param row: the team row for scope "team"
    :param group: position group key of GROUP_CHOICES
    :param sort: "Score", "Spec", "Elite" or a category name
    :param cells: what the category cells show, a key of CELL_CHOICES
    """
    data, info, profile, pcts = ctx.data, ctx.info, ctx.profile, ctx.pcts
    names = ctx.group_cats(group == "G")
    members = profile["Group"].isin(list(group))
    if scope == "fa":
        members &= info["TeamRow"].isna()
    elif scope == "team":
        members &= info["TeamRow"] == row
    ids = profile.index[members]
    if ids.empty:
        return View([note("No players in this selection.", level=WARNING)])
    key = pcts.loc[ids, sort] if sort in names else profile.loc[ids, sort]
    ids = key.sort_values(ascending=False, na_position="last",
                          kind="stable").index
    if scope != "team":
        ids = ids[:LEADERS_N]
    source = {"pct": pcts, "rate": ctx.rates, "total": ctx.totals}[cells]
    table = pd.concat([info.loc[ids, ["Player", "Pos", "Team", "GP",
                                      "Injury", "NoProj"]],
                       profile.loc[ids, ["Score", "Level", "Spec",
                                         "Elite", "Holes", "Type",
                                         "Best"]]], axis=1)
    for col in ("Level", "Spec"):
        table[col] = table[col].round(0).astype("Int64")
    for name in names:
        table[name] = _stat_column(name, source.loc[ids, name], cells)
    view = player_view(table, ["Player", "Pos", "Team", "GP", "Inj",
                               "Score", "Level", "Spec", "Elite",
                               "Holes", "Type", "Best", *names])
    # category cells are colored by percentile whatever they show
    tones = pd.concat([
        column_tones(view, {**PLAYER_TONES, "Level": percentile_tone,
                            "Elite": lambda v: diverging(v, 3),
                            "Holes": lambda v: diverging(-v, 3)}),
        pcts.loc[ids, names].map(percentile_tone).astype(object)
        .set_axis(view.index)], axis=1)
    where = {"all": "pool", "fa": "free agents",
             "team": data.team_names[row] if row is not None else ""}[scope]
    sort_label = f"{sort} percentile" if sort in names else sort
    blocks = [TableView(with_basis(
        f"Category leaderboard — {GROUP_CHOICES[group]}, "
        f"{where} (cells: {CELL_CHOICES[cells].lower()}, colored "
        f"by percentile; by {sort_label})", ctx.basis), view, tones),
        *ctx.profile_legend(table)]

    background = profile[profile["Group"].isin(list(group))]
    if background["Spec"].isna().all():
        blocks.append(note(f"No Level/Spec map: {GROUP_CHOICES[group]} "
                           f"have at most {PEAK_CATS} categories.",
                           level=INFO))
    else:
        blocks.append(FigureBlock("level_spec", "player_map", {
            "summary": background, "highlight": info.loc[ids, "Player"],
            "title": f"{data.config.name} — {GROUP_CHOICES[group]}: level vs "
                     f"specialization ({where}, {ctx.basis_short} stats, "
                     f"{data.config.year})"}))
    return View(blocks)


def player_labels(ctx: ReviewContext) -> dict[str, int]:
    """Unique label -> player id for picking players by name."""
    by_label: dict[str, int] = {}
    for pid in sorted(ctx.pool, key=lambda p: ctx.pool[p].name):
        player = ctx.pool[pid]
        label = (f"{player.name} "
                 f"({SLOT_ABBREV.get(player.position, player.position)}, "
                 f"{ctx.info.at[pid, 'Team']})")
        by_label[label if label not in by_label else f"{label} #{pid}"] = pid
    return by_label


def check_pick(ctx: ReviewContext, by_label: dict[str, int],
               picked: tuple[int, ...], text: str) -> bool | str:
    """Whether ``text`` is a valid next pick for a comparison of the
    ``picked`` players: True, or the reason it is not. Empty text ends the
    picking once two players are chosen."""
    if not text.strip():
        return True if len(picked) >= 2 else "Pick a player"
    pid = by_label.get(text)
    if pid is None:
        return "Pick a player from the list"
    if pid in picked:
        return "Already picked"
    if picked and ((ctx.profile.at[pid, "Group"] == "G")
                   != (ctx.profile.at[picked[0], "Group"] == "G")):
        return "Can't mix skaters and goalies"
    return True


def build_compare(ctx: ReviewContext, ids: tuple[int, ...]) -> View:
    """Per-category comparison of 2-4 skaters or goalies (player ids),
    their profile metrics and the percentile radar."""
    data, info, profile, pcts = ctx.data, ctx.info, ctx.profile, ctx.pcts
    basis = ctx.basis
    names = ctx.group_cats(profile.at[ids[0], "Group"] == "G")
    labels = [info.at[pid, "Player"] for pid in ids]
    if len(set(labels)) < len(labels):
        labels = [f"{name} ({info.at[pid, 'Team']})"
                  for name, pid in zip(labels, ids)]
    labels = [f"{label} {NO_PROJECTION}" if info.at[pid, "NoProj"]
              else label for label, pid in zip(labels, ids)]

    def cell(pid: int, name: str) -> str:
        # season totals only next to season rates; a ratio is its own total
        total = (_stat_text(name, ctx.totals.at[pid, name], per_game=False)
                 if basis.season_only and name not in RATIO_CATEGORIES
                 else "")
        return " · ".join(filter(None, (
            total, _stat_text(name, ctx.rates.at[pid, name], per_game=True),
            "" if pd.isna(pcts.at[pid, name])
            else f"{pcts.at[pid, name]:.0f}")))
    cells = pd.DataFrame({label: [cell(pid, name) for name in names]
                          for label, pid in zip(labels, ids)})
    cells.insert(0, "Cat", names)
    cells.index = range(1, len(cells) + 1)
    cell_tones = pd.DataFrame(
        {label: [percentile_tone(pcts.at[pid, name]) for name in names]
         for label, pid in zip(labels, ids)}, index=cells.index, dtype=object)

    metrics = ["Pos", "Team", "GP", "Score", "Level", "Peak", "Breadth",
               "Spec", "Elite", "Holes", "Type", "Best"]
    rows = pd.concat([info.loc[list(ids), ["Pos", "Team", "GP"]],
                      profile.loc[list(ids), metrics[3:]]], axis=1)
    text = {"Score": lambda v: f"{v:.2f}",
            **{m: lambda v: f"{v:.0f}"
               for m in ("Level", "Peak", "Breadth", "Spec")}}
    summary = pd.DataFrame(
        {label: ["" if pd.isna(rows.at[pid, m])
                 else text.get(m, str)(rows.at[pid, m]) for m in metrics]
         for label, pid in zip(labels, ids)})
    summary.insert(0, "Metric", metrics)
    summary.index = range(1, len(summary) + 1)
    toner = {"Score": score_tone, "Level": percentile_tone,
             "Peak": percentile_tone, "Breadth": percentile_tone}
    summary_tones = pd.DataFrame(
        {label: [toner[m](rows.at[pid, m]) if m in toner else None
                 for m in metrics]
         for label, pid in zip(labels, ids)}, index=summary.index,
        dtype=object)

    radar = pcts.loc[list(ids), names]
    radar.index = labels
    return View([
        TableView(with_basis(
            "Player comparison ("
            + ("season total · " if basis.season_only else "")
            + "per game · percentile within group)", basis),
            cells, cell_tones),
        TableView(with_basis("Profile summary", basis), summary,
                  summary_tones),
        *ctx.profile_legend(info.loc[list(ids)]),
        FigureBlock("category_radar", "player_radar", {
            "pcts": radar,
            "title": f"{data.config.name} — category percentiles "
                     f"({ctx.basis_short} stats, {data.config.year})"})])
