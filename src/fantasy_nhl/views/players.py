"""Player views: the player ranking and the player comparison."""
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

LEADERS_N = 30  # ranking rows (one team's roster: all)
COMPARE_MAX = 4  # players per comparison
GROUP_CHOICES = {"F": "Forwards", "D": "Defense", "FD": "Skaters (F + D)",
                 "G": "Goalies"}
CELL_CHOICES = {"pct": "Percentiles", "rate": "Per-game rates",
                "total": "Season totals"}
PROFILE_COLUMNS = ["Level", "Spec", "Elite", "Holes", "Type", "Best"]
# a comparison also shows what Spec is made of
COMPARE_COLUMNS = ["Level", "Peak", "Breadth", "Spec", "Elite", "Holes",
                   "Type", "Best"]
_PROFILE_TONES = {"Level": percentile_tone, "Peak": percentile_tone,
                  "Breadth": percentile_tone,
                  "Elite": lambda v: diverging(v, 3),
                  "Holes": lambda v: diverging(-v, 3)}


def leader_sorts(ctx: ReviewContext, group: str) -> list[str]:
    """What a ranking of that position group can be sorted by."""
    names = ctx.group_cats(group == "G")
    return ["Score"] + (["Spec"] if len(names) > PEAK_CATS else []) + [
        "Elite"] + names


def cell_choices(basis: StatBasis) -> dict[str, str]:
    """Ranking cell contents on offer (key -> label)."""
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
    """Numeric ranking cell column, rounded for display."""
    if cells == "pct":
        return values.round(0).astype("Int64")
    if cat == "SV%":
        return values.round(3)
    if cells == "rate" or cat in RATIO_CATEGORIES:
        return values.round(2)
    return values.round(0).astype("Int64")


def cells_label(cells: str) -> str:
    return f"cells: {CELL_CHOICES[cells].lower()}, colored by percentile"


def profile_columns(ctx: ReviewContext, ids, names: list[str], cells: str,
                    metrics: list[str] = PROFILE_COLUMNS
                    ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    The ranking's columns for the players ``ids``, in that order: the
    profile (``metrics``) and one column per category of ``names``.

    :param cells: what the category cells show, a key of CELL_CHOICES
    :return: (columns, their tones), indexed by player id; blank for a
        player outside the pool
    """
    ids = pd.Index(ids)
    columns = ctx.profile.reindex(index=ids, columns=metrics)
    for col in columns.columns.intersection(
            ["Level", "Peak", "Breadth", "Spec"]):
        columns[col] = columns[col].round(0).astype("Int64")
    for col in ("Type", "Best"):
        columns[col] = columns[col].fillna("")
    source = {"pct": ctx.pcts, "rate": ctx.rates, "total": ctx.totals}[cells]
    for name in names:
        columns[name] = _stat_column(name, source[name].reindex(ids), cells)
    # category cells are colored by percentile whatever they show
    tones = pd.concat([
        column_tones(columns, _PROFILE_TONES),
        ctx.pcts.reindex(index=ids, columns=names).map(percentile_tone)
        .astype(object)], axis=1)
    return columns, tones


def with_profile(ctx: ReviewContext, table: pd.DataFrame, view: pd.DataFrame,
                 tones: pd.DataFrame, cells: str | None,
                 goalies: bool | None = None
                 ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    A player table as displayed (``view``, ``tones``) with the ranking's
    columns appended; as it is without ``cells``.

    :param table: the rows behind ``view``, in its order, with PlayerId
    :param cells: what the category cells show, a key of CELL_CHOICES
    :param goalies: goalie (True) or skater (False) categories only;
        default: all, blank where they are not the player's
    """
    if cells is None:
        return view, tones
    names = ([cat.name for cat in ctx.cats] if goalies is None
             else ctx.group_cats(goalies))
    columns, column_tones_ = profile_columns(ctx, table["PlayerId"], names,
                                             cells)
    return (pd.concat([view, columns.set_axis(view.index)], axis=1),
            pd.concat([tones, column_tones_.set_axis(view.index)], axis=1))


def _ranking_rows(ctx: ReviewContext, ids, names: list[str], cells: str,
                  metrics: list[str] = PROFILE_COLUMNS
                  ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """The ranking's table of the players ``ids``, in that order.

    :return: (the rows behind it, the frame as displayed, its tones)
    """
    ids = list(ids)
    stats, stat_tones = profile_columns(ctx, ids, names, cells, metrics)
    table = pd.concat([ctx.info.loc[ids, ["Player", "Pos", "Team", "GP",
                                          "Injury", "NoProj"]],
                       ctx.profile.loc[ids, ["Score"]], stats], axis=1)
    view = player_view(table, ["Player", "Pos", "Team", "GP", "Inj",
                               "Score", *metrics, *names])
    tones = pd.concat([column_tones(view, PLAYER_TONES),
                       stat_tones.set_axis(view.index)], axis=1)
    return table, view, tones


def build_leaders(ctx: ReviewContext, scope: str, row: int | None,
                  group: str, sort: str, cells: str) -> View:
    """
    Player ranking with the level-vs-specialization map.

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
    table, view, tones = _ranking_rows(ctx, ids, names, cells)
    where = {"all": "pool", "fa": "free agents",
             "team": data.team_names[row] if row is not None else ""}[scope]
    sort_label = f"{sort} percentile" if sort in names else sort
    blocks = [TableView(with_basis(
        f"Player ranking — {GROUP_CHOICES[group]}, "
        f"{where} ({cells_label(cells)}; by {sort_label})", ctx.basis),
        view, tones),
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


def _by_category(ctx: ReviewContext, ids: tuple[int, ...], labels: list[str],
                 names: list[str]) -> TableView:
    """The compared players' stats, one row per category."""
    basis, pcts = ctx.basis, ctx.pcts

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
    tones = pd.DataFrame(
        {label: [percentile_tone(pcts.at[pid, name]) for name in names]
         for label, pid in zip(labels, ids)}, index=cells.index, dtype=object)
    return TableView(with_basis(
        "Player comparison ("
        + ("season total · " if basis.season_only else "")
        + "per game · percentile within group)", basis),
        cells, tones, fixed=True)


def _profile_summary(ctx: ReviewContext, ids: tuple[int, ...],
                     labels: list[str]) -> TableView:
    """The compared players' profile metrics, one column per player."""
    metrics = ["Pos", "Team", "GP", "Score", *COMPARE_COLUMNS]
    rows = pd.concat([ctx.info.loc[list(ids), ["Pos", "Team", "GP"]],
                      ctx.profile.loc[list(ids), metrics[3:]]], axis=1)
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
    tones = pd.DataFrame(
        {label: [toner[m](rows.at[pid, m]) if m in toner else None
                 for m in metrics]
         for label, pid in zip(labels, ids)}, index=summary.index,
        dtype=object)
    return TableView(with_basis("Profile summary", ctx.basis), summary,
                     tones, fixed=True)


def build_compare(ctx: ReviewContext, ids: tuple[int, ...],
                  cells: str | None = None) -> View:
    """Comparison of 2-4 skaters or goalies (player ids): their stats by
    category, their profile metrics and the percentile radar.

    :param cells: show one table instead of the two, the players' rows of
        the ranking, their category cells showing this key of CELL_CHOICES
    """
    data, info, pcts = ctx.data, ctx.info, ctx.pcts
    names = ctx.group_cats(ctx.profile.at[ids[0], "Group"] == "G")
    labels = [info.at[pid, "Player"] for pid in ids]
    if len(set(labels)) < len(labels):
        labels = [f"{name} ({info.at[pid, 'Team']})"
                  for name, pid in zip(labels, ids)]
    # namesakes on one team: tell them apart like the pick list does
    labels = [f"{label} #{pid}" if label in labels[:i] else label
              for i, (label, pid) in enumerate(zip(labels, ids))]
    labels = [f"{label} {NO_PROJECTION}" if info.at[pid, "NoProj"]
              else label for label, pid in zip(labels, ids)]

    if cells:
        _, view, tones = _ranking_rows(ctx, ids, names, cells, COMPARE_COLUMNS)
        tables = [TableView(with_basis(
            f"Compared players ({cells_label(cells)})", ctx.basis), view,
            tones)]
    else:
        tables = [_by_category(ctx, ids, labels, names),
                  _profile_summary(ctx, ids, labels)]
    radar = pcts.loc[list(ids), names]
    radar.index = labels
    return View([
        *tables,
        *ctx.profile_legend(info.loc[list(ids)]),
        FigureBlock("category_radar", "player_radar", {
            "pcts": radar,
            "title": f"{data.config.name} — category percentiles "
                     f"({ctx.basis_short} stats, {data.config.year})"})])
