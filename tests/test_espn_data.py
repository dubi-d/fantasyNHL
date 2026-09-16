"""Schedule-calendar regressions using ESPN-shaped data, without live requests."""
import json
from datetime import date, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from espn_api.hockey import League

from fantasy_nhl import espn_data
from fantasy_nhl.config import LeagueConfig


@pytest.fixture
def calendar_2027():
    # ESPN segment 0, period type 2: week 19 spans Feb 1–14, not Feb 1–7.
    periods = []
    start = 1
    for week in range(1, 28):
        length = 6 if week == 1 else 14 if week == 19 else 7
        end = min(start + length - 1, 194)
        periods.append({"id": week, "scoringPeriodStart": start,
                        "scoringPeriodEnd": end})
        start = end + 1
    return periods


def _html(periods, year=2027, script=False):
    constants = {"seasonConfig": year, "segments": [{"id": 0, "periodTypes": [
        {"id": 2, "weekly": True, "periods": periods}]}]}
    payload = json.dumps({"props": {"pageProps": {"page": {
        "config": {"constants": constants}}}}})
    if script:
        return f'<script type="application/json" id="__NEXT_DATA__">{payload}</script>'
    return f'<script>__NEXT_DATA__ = {payload}; next.init();</script>'


def _parse(html, year=2027, period_type_id=2):
    return espn_data._season_periods(espn_data._app_constants(html), year,
                                    period_type_id)


def _league() -> League:
    anchor = datetime(2026, 9, 29, 19, tzinfo=ZoneInfo("America/New_York"))
    return cast(League, SimpleNamespace(
        firstScoringPeriod=1, finalScoringPeriod=181,
        currentMatchupPeriod=1, matchup_ids={1: ["1"]},
        settings=SimpleNamespace(
            reg_season_count=22, playoff_matchup_period_length=1,
            matchup_periods={str(w): [w] for w in range(1, 26)},
            _raw_schedule_settings={"periodTypeId": 2}),
        _get_all_pro_schedule=Mock(return_value={
            "1": {"1": [{"date": anchor.timestamp() * 1000}]}}),
    ))


def _data(league):
    return espn_data.LeagueData(
        config=LeagueConfig("Test", 42, 2027, "", ""), team_names=[],
        current_week=1, weekly_cat_scores=np.zeros((0, 0, 1)),
        weekly_results=[], total_weeks=25, regular_weeks=22,
        espn_league=league,
    )


def test_2027_playoffs_follow_extended_matchup(monkeypatch, calendar_2027):
    periods = {p["id"]: list(range(p["scoringPeriodStart"],
                                   p["scoringPeriodEnd"] + 1))
               for p in calendar_2027}
    fetch = Mock(return_value=periods)
    monkeypatch.setattr(espn_data, "_fetch_season_periods", fetch, raising=False)
    data = _data(_league())
    dates = espn_data.fetch_week_dates(data)
    assert dates[19] == (date(2027, 2, 1), date(2027, 2, 14))
    assert dates[22] == (date(2027, 3, 1), date(2027, 3, 7))
    assert dates[23] == (date(2027, 3, 8), date(2027, 3, 14))
    assert dates[24] == (date(2027, 3, 15), date(2027, 3, 21))
    assert dates[25] == (date(2027, 3, 22), date(2027, 3, 28))
    assert len(dates) == 25  # NHL weeks beyond the fantasy season stay excluded.
    schedule = espn_data.fetch_schedule_data(data)
    assert [p for ps in schedule.week_periods.values() for p in ps] == list(range(1, 182))
    assert espn_data.fetch_week_dates(data) is dates
    fetch.assert_called_once_with(2027, 2)
    assert data.espn_league is not None
    cast(Mock, data.espn_league._get_all_pro_schedule).assert_called_once()


@pytest.mark.parametrize("script", [False, True])
def test_parse_espn_calendar(calendar_2027, script):
    periods = _parse(_html(calendar_2027, script=script))
    assert periods[1] == list(range(1, 7))
    assert periods[19] == list(range(126, 140))
    assert periods[23] == list(range(161, 168))


@pytest.mark.parametrize("html", ["<html>Unavailable</html>",
                                 "<script>__NEXT_DATA__ = {broken;</script>",
                                 '<script>__NEXT_DATA__ = {};</script>'])
def test_missing_or_changed_calendar_fails_explicitly(html):
    with pytest.raises(ValueError, match="ESPN.*calendar"):
        _parse(html)


def test_wrong_season_is_not_silently_used(calendar_2027):
    with pytest.raises(ValueError, match="ESPN.*calendar"):
        _parse(_html(calendar_2027, year=2026))


def test_unknown_period_type_is_rejected(calendar_2027):
    with pytest.raises(ValueError, match="ESPN.*calendar"):
        _parse(_html(calendar_2027), period_type_id=99)


def test_public_calendar_request_has_timeout_and_no_cookies(monkeypatch, calendar_2027):
    request = Mock(return_value=BytesIO(_html(calendar_2027).encode()))
    monkeypatch.setattr(espn_data, "urlopen", request)
    assert espn_data._fetch_season_periods(2027, 2)[23] == list(range(161, 168))
    args, kwargs = request.call_args
    assert args[0].full_url.endswith("schedule?seasonId=2027")
    assert not args[0].has_header("Cookie")
    assert kwargs == {"timeout": 30}


def test_public_calendar_timeout_is_explained(monkeypatch):
    monkeypatch.setattr(espn_data, "urlopen", Mock(side_effect=TimeoutError))
    with pytest.raises(ValueError, match="Unable to load ESPN season calendar"):
        espn_data._fetch_season_periods(2027, 2)


@pytest.mark.parametrize("periods", [[],
    [{"id": 1, "scoringPeriodStart": 7, "scoringPeriodEnd": 1}],
    [{"id": 1, "scoringPeriodStart": 1, "scoringPeriodEnd": 7},
     {"id": 1, "scoringPeriodStart": 8, "scoringPeriodEnd": 14}],
    [{"id": 1, "scoringPeriodStart": 1, "scoringPeriodEnd": 7},
     {"id": 2, "scoringPeriodStart": 7, "scoringPeriodEnd": 14}],
])
def test_invalid_calendar_ranges_are_rejected(periods):
    with pytest.raises(ValueError, match="ESPN.*calendar"):
        _parse(_html(periods))


@pytest.mark.parametrize("year", [2025, 2026])
@pytest.mark.parametrize("protocol_relative", [False, True])
def test_archived_season_uses_its_own_calendar(
        monkeypatch, calendar_2027, year, protocol_relative):
    base = "https://cdn1.espn.net/kona/build/_next/"
    main_url = base + "static/commons/main-abcd.js"
    src = main_url.removeprefix("https:") if protocol_relative else main_url
    html = _html(calendar_2027) + f'<script src="{src}"></script>'
    name = f"chunks/modules_api_lm_seasons_fhl_{year}_abc123"
    digest = "a" * 20
    bundle = f'{{48:"{name}"}}[t]+"-"+{{48:"{digest}"}}[t]+".js"'
    source = ('Object.assign({},data,{seasonConfig:' + str(year) + '});'
              '4649:function(e,a){e.exports=[{id:0,periodTypes:[{id:2,'
              'weekly:true,periods:[{id:1,scoringPeriodStart:1,'
              'scoringPeriodEnd:14}]}]}]}});')
    read = Mock(side_effect=[html, bundle, source])
    monkeypatch.setattr(espn_data, "_read_calendar_resource", read)
    assert espn_data._fetch_season_periods(year, 2) == {1: list(range(1, 15))}
    assert [call.args[0] for call in read.call_args_list] == [
        f"https://fantasy.espn.com/hockey/league/schedule?seasonId={year}",
        main_url, base + f"webpack/{name}-{digest}.js"]


def test_missing_archive_does_not_use_current_season(monkeypatch, calendar_2027):
    monkeypatch.setattr(espn_data, "_read_calendar_resource",
                        Mock(return_value=_html(calendar_2027)))
    with pytest.raises(ValueError, match="ESPN archived calendar for 2026"):
        espn_data._fetch_season_periods(2026, 2)


def test_calendar_resources_are_restricted_to_public_espn(monkeypatch):
    request = Mock()
    monkeypatch.setattr(espn_data, "urlopen", request)
    with pytest.raises(ValueError, match="Unexpected ESPN calendar resource"):
        espn_data._read_calendar_resource("https://example.com/calendar.js")
    request.assert_not_called()


def test_league_matchups_combine_base_periods():
    league = _league()
    league.settings.matchup_periods = {"1": [1], "2": [2, 3], "3": [4, 5]}
    league.currentMatchupPeriod = 3
    league.matchup_ids = {}  # archived seasons need no scored-day history.
    dates = {p: date(2027, 1, 4) + timedelta(days=p - 1) for p in range(1, 36)}
    base = {w: list(range((w - 1) * 7 + 1, w * 7 + 1)) for w in range(1, 6)}
    result = espn_data._week_scoring_periods(league, dates, base)
    assert result == {1: list(range(1, 8)), 2: list(range(8, 22)),
                      3: list(range(22, 36))}


def test_missing_base_period_fails_instead_of_guessing():
    with pytest.raises(ValueError, match="ESPN.*calendar"):
        espn_data._week_scoring_periods(_league(), {1: date(2026, 9, 29)}, {})


def test_fetch_failure_does_not_cache_guessed_dates(monkeypatch):
    monkeypatch.setattr(espn_data, "_fetch_season_periods",
                        Mock(side_effect=ValueError("ESPN calendar unavailable")))
    data = _data(_league())
    with pytest.raises(ValueError, match="ESPN calendar"):
        espn_data.fetch_week_dates(data)
    assert data.schedule is None
    assert data.week_dates is None