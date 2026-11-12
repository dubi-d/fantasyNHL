"""NHL schedule outlook per fantasy matchup, and its scoring calibration."""
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd

from ..analysis import (
    OFF_NIGHT_MAX_TEAMS,
    PreviewPlayer,
    calibrate_night_value,
    effective_games,
    night_seat_curve,
    off_night_periods,
    open_seat_counts,
    schedule_summary,
    team_week_schedule,
)
from ..config import ScheduleCalibration
from .model import INFO, FigureBlock, TableView, Tone, View, column_tones, heat, note

if TYPE_CHECKING:
    from ..espn_data import CalibrationData, LeagueData, ScheduleData

SCOPE_LABELS = {"full": "full season", "remaining": "remaining matchups",
                "playoffs": "playoffs"}
NEAR_WEEKS = 4  # matchups the near-term columns of "remaining" cover
_COMBINED_REST = "Combined rest of season"


@dataclass
class ScheduleSelection:
    scope: str  # key of SCOPE_LABELS
    selected: list[int]  # matchup weeks in scope
    week_periods: dict[int, list[int]]  # their scoring periods, if any
    playoff_weeks: set[int]
    near_weeks: list[int] | None  # near-term weeks ("remaining" only)
    score_periods: dict[int, list[int]]  # weeks the leading score covers

    @property
    def blends_playoffs(self) -> bool:
        """Whether the scope mixes regular-season and playoff weeks."""
        return self.scope != "playoffs" and any(
            w in self.week_periods for w in self.playoff_weeks)


def select_schedule(data: "LeagueData", schedule: "ScheduleData",
                    scope: str) -> ScheduleSelection | None:
    """The matchup weeks of a scope; None if it holds no matchups."""
    playoff_weeks = {w for w in schedule.week_periods
                     if 0 < data.regular_weeks < w}
    selected = sorted(schedule.week_periods)
    if scope == "remaining":
        selected = [w for w in selected if w >= data.current_week]
    elif scope == "playoffs":
        selected = [w for w in selected if w in playoff_weeks]
    week_periods = {w: schedule.week_periods[w] for w in selected
                    if schedule.week_periods[w]}
    if not week_periods:
        return None
    # playoffs-only scope: PO columns would just duplicate the totals
    near_weeks = selected[:NEAR_WEEKS] if scope == "remaining" else None
    # effective-games score: near-term for remaining, whole scope otherwise
    score_weeks = near_weeks or selected
    return ScheduleSelection(
        scope, selected, week_periods, playoff_weeks, near_weeks,
        {w: week_periods[w] for w in score_weeks if w in week_periods})


def roster_fit(playing_by_period: dict[int, set[str]],
               week_periods: dict[int, list[int]],
               roster: list[PreviewPlayer],
               slot_counts: dict[str, int]) -> pd.Series:
    """Fit score: effective games weighted by a roster's actual open
    skater seats instead of the generic night value."""
    periods = sorted({p for ps in week_periods.values() for p in ps})
    seats = {p: skater for p, (skater, _) in
             open_seat_counts(roster, slot_counts, playing_by_period,
                              periods).items()}
    return effective_games(playing_by_period, week_periods, seats)


def schedule_scores(schedule: "ScheduleData", selection: ScheduleSelection,
                    calibration: ScheduleCalibration | None,
                    playoff_weight: float,
                    fit: pd.Series | None = None) -> dict[str, pd.Series]:
    """
    The effective-games score columns of a scope, in display order.

    :param calibration: night-value curve (None = linear proxy)
    :param playoff_weight: weight of the playoff score in Combined
    :param fit: a roster's Fit score to lead with (see roster_fit)
    """
    playing = schedule.playing_by_period
    week_periods = selection.week_periods
    score_wp = selection.score_periods
    playoff_weeks = selection.playoff_weeks
    curve_fn = night_seat_curve(calibration.curve if calibration else None)
    seats_generic = {p: curve_fn(len(teams))
                     for p, teams in playing.items() if teams}

    def blend(a: pd.Series, b: pd.Series) -> pd.Series:
        return (1 - playoff_weight) * a + playoff_weight * b

    if selection.scope == "playoffs":
        # already playoff-only: no Reg Score/PO Score/Combined split needed
        scores = {"Score": effective_games(playing, score_wp, seats_generic)}
        return scores if fit is None else {"Fit": fit, **scores}

    po_wp = {w: week_periods[w] for w in playoff_weeks if w in week_periods}
    reg_wp = {w: p for w, p in score_wp.items() if w not in playoff_weeks}
    if selection.scope == "full":
        scores = {"Reg Score": effective_games(playing, reg_wp, seats_generic)}
        if po_wp:
            scores["PO Score"] = effective_games(playing, po_wp, seats_generic)
            scores = {"Combined": blend(scores["Reg Score"],
                                        scores["PO Score"]), **scores}
        return scores

    near_n = len(score_wp)
    scores = {f"Reg Score next {near_n}": effective_games(
        playing, reg_wp, seats_generic)}
    rest_wp = {w: p for w, p in week_periods.items()
               if w not in playoff_weeks and w not in score_wp}
    if rest_wp:
        scores["Reg Score rest"] = effective_games(playing, rest_wp,
                                                   seats_generic)
    if po_wp:
        scores["PO Score"] = effective_games(playing, po_wp, seats_generic)
        # Combined uses the WHOLE remaining regular season, not just
        # the "rest" portion (near-term N is informational only)
        all_reg_wp = {w: p for w, p in week_periods.items()
                      if w not in playoff_weeks}
        reg_score_all = effective_games(playing, all_reg_wp, seats_generic)
        scores[_COMBINED_REST] = blend(reg_score_all, scores["PO Score"])
    return scores if fit is None else {f"Fit next {near_n}": fit, **scores}


def lead_choices(selection: ScheduleSelection,
                 scores: dict[str, pd.Series]) -> list[str]:
    """Score columns the table of a scope can be sorted by (the first
    one is the default); empty where the order is fixed."""
    if selection.scope != "remaining":
        return []
    near_n = len(selection.score_periods)
    return [key for key in (f"Fit next {near_n}", _COMBINED_REST,
                            f"Reg Score next {near_n}") if key in scores]


def lead_with(scores: dict[str, pd.Series],
              lead: str) -> dict[str, pd.Series]:
    """The score columns with ``lead`` moved first."""
    return {lead: scores[lead],
            **{key: s for key, s in scores.items() if key != lead}}


def _range_tones(values, span: pd.Series) -> list[Tone]:
    """Tones stretching the actual value range of ``span`` over the full
    gradient; none when it is constant."""
    lo, hi = float(span.min()), float(span.max())
    if hi <= lo:
        return [None] * len(values)
    return [heat((v - lo) / (hi - lo)) for v in values]


def build_schedule_outlook(data: "LeagueData", schedule: "ScheduleData",
                           selection: ScheduleSelection,
                           scores: dict[str, pd.Series],
                           calibration: ScheduleCalibration | None,
                           playoff_weight: float, fitted: bool) -> View:
    """
    Per-NHL-team games and off-night games over a scope's matchups: summary
    table (week-by-week for the playoffs) and the teams-x-matchups figure.

    :param scores: score columns, the first one leading the sort
    :param calibration: the calibration behind the scores, for the legend
    :param fitted: whether the scores include a roster's Fit
    """
    scope, playoff_weeks = selection.scope, selection.playoff_weeks
    off_periods = off_night_periods(schedule.playing_by_period)
    games_df, off_df = team_week_schedule(schedule.playing_by_period,
                                          selection.week_periods, off_periods)
    summary = schedule_summary(
        games_df, off_df, set() if scope == "playoffs" else playoff_weeks,
        near_weeks=selection.near_weeks, scores=scores)
    tones = {col: _range_tones(summary[col], summary[col])
             for col in summary.columns if col != "Team"}
    summary.index = range(1, len(summary) + 1)  # sorted by analysis
    order = list(summary["Team"])  # same sorting in the figure
    off_label = f"off-night = ≤{OFF_NIGHT_MAX_TEAMS} teams playing"
    scope_label = SCOPE_LABELS[scope]

    if scope == "playoffs":
        # few columns: append the week-by-week grid as games (off-nights),
        # colored by the off-night count
        totals_g = games_df.sum(axis=1)
        totals_o = off_df.sum(axis=1)
        for name, games, off in (
                *((f"M{w}", games_df[w], off_df[w]) for w in games_df.columns),
                ("Total", totals_g, totals_o)):
            summary[name] = [f"{games[t]} ({off[t]})" for t in order]
            tones[name] = _range_tones([off[t] for t in order], off)

    calib_note = (f"calibrated on {calibration.source} "
                  f"({calibration.calibrated})" if calibration else
                  "uncalibrated (linear proxy) — "
                  "pick 'Calibrate scoring' in the scope menu")
    fit_note = " Fit uses your roster's actual open seats." if fitted else ""
    po_note = (f" PO Score/Combined isolate playoff-week schedule "
               f"strength ({round((1 - playoff_weight) * 100)}/"
               f"{round(playoff_weight * 100)} blend)."
               if "PO Score" in scores else "")
    score_label = "Score" if scope == "playoffs" else "Reg Score"

    figure = {"games": games_df.loc[order], "off": off_df.loc[order],
              "off_label": off_label,
              "title": (f"{data.config.name} — NHL Schedule ({scope_label}, "
                        f"{data.config.year})"),
              "scores": {name: s.reindex(order) for name, s in scores.items()}}
    if scope != "playoffs":
        figure["playoff_weeks"] = playoff_weeks
    return View([
        TableView(f"NHL Schedule Outlook ({scope_label}, "
                  f"matchups {selection.selected[0]}–{selection.selected[-1]}, "
                  f"{off_label})", summary,
                  pd.DataFrame(tones, index=summary.index, dtype=object)),
        note(f"{score_label} = effective games per matchup, games "
             f"on streamable nights count up to double; "
             f"{calib_note}.{po_note}{fit_note}", level=INFO),
        FigureBlock("schedule_combined" if scope == "playoffs"
                    else "schedule_heatmap", f"schedule_{scope}", figure)])


def build_calibration(source_name: str, calibration_data: "CalibrationData",
                      ) -> tuple[View, dict[int, float]]:
    """Fit the night-value curve on a league season; returns its table and
    the curve itself (teams playing -> mean capped open skater seats)."""
    curve = calibrate_night_value(calibration_data.rosters,
                                  calibration_data.slot_counts,
                                  calibration_data.playing_by_period)
    nights = {n: 0 for n in curve}
    for teams in calibration_data.playing_by_period.values():
        if teams:
            nights[len(teams)] += 1
    table = pd.DataFrame({
        "Teams playing": list(curve),
        "Avg open seats": [round(v, 2) for v in curve.values()],
        "Nights": [nights[n] for n in curve],
    })
    table.index = range(1, len(table) + 1)
    return View([TableView(
        f"Night value curve from {source_name} "
        f"({len(calibration_data.rosters)} rosters)", table,
        column_tones(table, {"Avg open seats": lambda v: heat(v / 3)}))]), curve
