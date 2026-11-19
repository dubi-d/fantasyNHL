"""The NHL stats download and the reading of its files, on stubbed API
answers: nothing asks the NHL."""
import csv
import json
from datetime import date, timedelta
from io import BytesIO
from unittest.mock import Mock
from urllib.error import URLError

import pytest

from fantasy_nhl.cli import history as command
from fantasy_nhl.sources.nhl import history

SEASON = "seasonId=20212022 and gameTypeId=2"


def _skater(player_id, name="Skater", position="C", teams="EDM", **stats):
    return {"playerId": player_id, "skaterFullName": name,
            "positionCode": position, "teamAbbrevs": teams,
            "gamesPlayed": 80, "goals": 44, "assists": 79, "ppPoints": 44,
            "shPoints": 1, "shots": 314, **stats}


def _realtime(player_id, hits=75, blocks=27):
    return {"playerId": player_id, "hits": hits, "blockedShots": blocks}


def _goalie(player_id, name="Goalie", **stats):
    return {"playerId": player_id, "goalieFullName": name, "teamAbbrevs": "WPG",
            "gamesPlayed": 66, "gamesStarted": 66, "wins": 29, "losses": 27,
            "otLosses": 10, "shotsAgainst": 2155, "saves": 1962,
            "goalsAgainst": 193, "goalsAgainstAverage": 2.96656,
            "savePct": 0.91044, "shutouts": 4, **stats}


def _answer(*rows, total=None):
    return {"data": list(rows), "total": len(rows) if total is None else total}


@pytest.fixture
def reports(monkeypatch):
    """The three reports of a season; a test replaces what it needs."""
    answers = {
        "skater/summary": _answer(
            _skater(8478402, "Connor McDavid"),
            _skater(8474568, "Luke Schenn", "D", "VAN,TOR")),
        "skater/realtime": _answer(_realtime(8474568, 318, 98),
                                   _realtime(8478402)),
        "goalie/summary": _answer(_goalie(8476945, "Connor Hellebuyck")),
    }
    get = Mock(side_effect=lambda resource, *timeout, **params:
               answers[resource])
    monkeypatch.setattr(history, "_get", get)
    answers["get"] = get
    return answers


def test_seasons_are_named_by_the_year_they_end_in(tmp_path):
    assert history.season_id(2026) == 20252026
    assert history.season_label(2026) == "2025-26"
    assert history.season_label(2000) == "1999-00"
    assert history.season_path(2026, tmp_path) == (
        tmp_path / "season_20252026.csv")


def test_a_season_is_one_row_per_player(reports):
    rows = history.fetch_season_stats(2022)
    assert [row["name"] for row in rows] == [
        "Luke Schenn", "Connor McDavid", "Connor Hellebuyck"]
    assert rows[0] == {
        "season": 20212022, "player_id": 8474568, "name": "Luke Schenn",
        "position": "D", "teams": "VAN,TOR", "GP": 80, "G": 44, "A": 79,
        "PPP": 44, "SHP": 1, "SOG": 314, "HIT": 318, "BLK": 98}
    assert rows[2] == {
        "season": 20212022, "player_id": 8476945,
        "name": "Connor Hellebuyck", "position": "G", "teams": "WPG",
        "GP": 66, "GS": 66, "W": 29, "L": 27, "OTL": 10, "SA": 2155,
        "SV": 1962, "GA": 193, "GAA": 2.96656, "SV%": 0.91044, "SO": 4}


def test_every_other_field_is_kept_under_its_nhl_name(reports):
    reports["skater/summary"] = _answer(_skater(
        1, seasonId=20212022, penaltyMinutes=45, timeOnIcePerGame=1323.975))
    reports["skater/realtime"] = _answer({
        **_realtime(1), "gamesPlayed": 80, "timeOnIcePerGame": 1323.98,
        "takeaways": 70, "totalShotAttempts": None})
    reports["goalie/summary"] = _answer(_goalie(
        2, goals=0, assists=2, timeOnIce=234210))
    skater, goalie = history.fetch_season_stats(2022)
    assert set(skater) - set(history.COLUMNS) == {
        "penaltyMinutes", "timeOnIcePerGame", "takeaways",
        "totalShotAttempts"}
    assert (skater["penaltyMinutes"], skater["timeOnIcePerGame"],
            skater["takeaways"], skater["totalShotAttempts"]) == (
        45, 1323.975, 70, None)
    assert set(goalie) - set(history.COLUMNS) == {"timeOnIce"}
    assert (goalie["G"], goalie["A"], goalie["timeOnIce"]) == (0, 2, 234210)


def test_whole_regular_season_reports_are_requested(reports):
    history.fetch_season_stats(2022)
    assert [call.args for call in reports["get"].call_args_list] == [
        ("skater/summary", 30), ("skater/realtime", 30),
        ("goalie/summary", 30)]
    assert all(call.kwargs == {"limit": -1, "cayenneExp": SEASON}
               for call in reports["get"].call_args_list)


@pytest.mark.parametrize("report, answer, message", [
    ("goalie/summary", _answer(_goalie(1), total=2), "incomplete"),
    ("goalie/summary", _answer(_goalie(1), _goalie(1)), "incomplete"),
    ("goalie/summary", {"rows": []}, "unexpected"),
    ("skater/realtime", _answer(_realtime(8478402), _realtime(1)),
     "different players"),
    ("goalie/summary", _answer({"playerId": 1, "teamAbbrevs": "WPG"}),
     "no longer reports gamesPlayed, gamesStarted, goalieFullName, "),
    ("skater/realtime", _answer({"playerId": 8474568, "hits": 318},
                                _realtime(8478402)),
     "no longer reports blockedShots\\."),
])
def test_a_report_that_cannot_be_trusted_is_refused(reports, report, answer,
                                                    message):
    reports[report] = answer
    with pytest.raises(history.NhlStatsError, match=message):
        history.fetch_season_stats(2022)


def test_request_goes_to_the_stats_api_with_a_timeout(monkeypatch):
    request = Mock(return_value=BytesIO(json.dumps(_answer()).encode()))
    monkeypatch.setattr(history, "urlopen", request)
    assert history._get("skater/summary", limit=-1, cayenneExp=SEASON) == (
        _answer())
    args, kwargs = request.call_args
    assert args[0].full_url == (
        "https://api.nhle.com/stats/rest/en/skater/summary?limit=-1"
        "&cayenneExp=seasonId%3D20212022+and+gameTypeId%3D2")
    assert kwargs == {"timeout": 30}


@pytest.mark.parametrize("failure", [
    Mock(side_effect=URLError("down")), Mock(side_effect=TimeoutError),
    Mock(return_value=BytesIO(b"<html>not json"))])
def test_a_failed_request_is_explained(monkeypatch, failure):
    monkeypatch.setattr(history, "urlopen", failure)
    with pytest.raises(history.NhlStatsError, match="Unable to read 'season'"):
        history._get("season")


def test_season_dates_are_keyed_by_closing_year(monkeypatch):
    get = Mock(return_value={"data": [
        {"id": 20252026, "startDate": "2025-10-07T17:00:00",
         "regularSeasonEndDate": "2026-04-17T00:00:00"},
        {"id": 20262027, "startDate": "2026-09-29T17:00:00",
         "regularSeasonEndDate": "2027-04-10T00:00:00"}]})
    monkeypatch.setattr(history, "_get", get)
    assert history.fetch_season_dates() == {
        2026: (date(2025, 10, 7), date(2026, 4, 17)),
        2027: (date(2026, 9, 29), date(2027, 4, 10))}
    history.fetch_season_dates(timeout=5)
    assert [call.args for call in get.call_args_list] == [
        ("season", 30), ("season", 5)]
    # the last games end a day later east of North America
    assert history.final_day(date(2026, 4, 17)) == date(2026, 4, 19)


def test_an_unexpected_season_list_is_refused(monkeypatch):
    monkeypatch.setattr(history, "_get", Mock(return_value={"data": [
        {"id": 20252026, "regularSeasonEndDate": "2026-04-17T00:00:00"}]}))
    with pytest.raises(history.NhlStatsError, match="season list"):
        history.fetch_season_dates()


DATES = {2022: (date(2021, 10, 12), date(2022, 4, 29)),
         2023: (date(2022, 10, 7), date(2023, 4, 14))}


@pytest.fixture
def dates(monkeypatch):
    stub = Mock(return_value=DATES)
    monkeypatch.setattr(history, "fetch_season_dates", stub)
    return stub


def _files(folder):
    return sorted(path.name for path in folder.iterdir())


def test_the_current_season_is_stored_apart_from_the_finished(
        reports, dates, tmp_path):
    assert history.current_file(tmp_path) is None
    with pytest.raises(history.NhlStatsError, match="no season"):
        history.refresh_current_season(tmp_path, date(2021, 10, 11))
    path = history.refresh_current_season(tmp_path, date(2021, 10, 12))
    assert path == tmp_path / "current_20212022.csv" == (
        history.current_file(tmp_path))
    assert dates.call_args.kwargs == {"timeout": 10}
    assert [call.args for call in reports["get"].call_args_list] == [
        ("skater/summary", 10), ("skater/realtime", 10),
        ("goalie/summary", 10)]
    # no season of the history, and nothing the command takes for stored
    assert history.stored_seasons(tmp_path) == []
    assert history.read_history(tmp_path).empty
    assert not history.season_path(2022, tmp_path).exists()

    current = history.read_current_season(path)
    assert current.season == 20212022
    assert current.stats["name"].tolist() == [
        "Luke Schenn", "Connor McDavid", "Connor Hellebuyck"]
    assert list(current.stats.columns) == history.COLUMNS
    assert current.loaded.tzinfo and abs(
        current.loaded.timestamp() - path.stat().st_mtime) < 1

    # the finished season replaces it, and is not downloaded as current
    history.save_season_stats(2022, history.fetch_season_stats(2022),
                              tmp_path)
    assert _files(tmp_path) == ["season_20212022.csv"]
    requests = reports["get"].call_count
    assert history.refresh_current_season(tmp_path, date(2022, 1, 15)) is None
    assert reports["get"].call_count == requests
    assert history.current_file(tmp_path) is None


def test_a_season_whose_totals_are_final_is_stored_as_finished(
        reports, dates, tmp_path):
    # on the day after its last games it is still the current one
    path = history.refresh_current_season(tmp_path, date(2022, 4, 30))
    assert _files(tmp_path) == [path.name] == ["current_20212022.csv"]
    assert history.refresh_current_season(tmp_path, date(2022, 5, 1)) is None
    assert _files(tmp_path) == ["season_20212022.csv"]
    assert history.read_history(tmp_path)["name"].tolist() == [
        "Luke Schenn", "Connor McDavid", "Connor Hellebuyck"]

    # also without a file from while it was played, and only once
    other = tmp_path / "other"
    assert history.refresh_current_season(other, date(2022, 7, 1)) is None
    assert _files(other) == ["season_20212022.csv"]
    requests = reports["get"].call_count
    assert history.refresh_current_season(other, date(2022, 7, 2)) is None
    assert reports["get"].call_count == requests


def test_a_season_left_unfinished_is_stored_once_the_next_one_runs(
        reports, dates, tmp_path):
    history.refresh_current_season(tmp_path, date(2022, 4, 1))
    path = history.refresh_current_season(tmp_path, date(2022, 11, 1))
    assert _files(tmp_path) == ["current_20222023.csv",
                                "season_20212022.csv"]
    assert path == history.current_file(tmp_path)
    assert history.read_current_season(path).season == 20222023


def test_a_failed_final_download_keeps_the_current_file(reports, dates,
                                                        tmp_path):
    history.refresh_current_season(tmp_path, date(2022, 4, 1))
    reports["goalie/summary"] = _answer(_goalie(1), total=2)
    with pytest.raises(history.NhlStatsError, match="incomplete"):
        history.refresh_current_season(tmp_path, date(2022, 6, 1))
    assert _files(tmp_path) == ["current_20212022.csv"]


def test_the_stored_current_season_is_the_newest_unfinished(tmp_path):
    for name in ("current_20242025.csv", "current_20252026.csv",
                 "current_2026.csv", "current_20252026.part"):
        (tmp_path / name).write_text("player,goals\nA,1\n")
    newest = tmp_path / "current_20252026.csv"
    assert history.current_file(tmp_path) == newest
    with pytest.raises(history.NhlStatsError,
                       match="refresh the current season"):
        history.read_current_season(newest)
    # a leftover of a season that is stored as finished does not count
    history.save_season_stats(2026, [], tmp_path)
    (tmp_path / "current_20252026.csv").write_text("")
    assert history.current_file(tmp_path) is None


def test_a_season_is_stored_as_csv(reports, tmp_path):
    reports["skater/summary"]["data"][0]["penaltyMinutes"] = 45
    reports["goalie/summary"] = _answer(_goalie(
        1, "No Shots", savePct=None, goalsAgainstAverage=None, timeOnIce=60))
    stale = history.season_path(2022, tmp_path)
    stale.write_text("old")
    path = history.save_season_stats(
        2022, history.fetch_season_stats(2022), tmp_path)
    assert path == stale and [p.name for p in tmp_path.iterdir()] == [
        "season_20212022.csv"]
    with path.open(newline="", encoding="utf-8") as file:
        header, schenn, mcdavid, goalie = csv.reader(file)
    assert history.COLUMNS == [
        "season", "player_id", "name", "position", "teams", "GP", "G", "A",
        "PPP", "SHP", "SOG", "HIT", "BLK", "GS", "W", "L", "OTL", "SA",
        "SV", "GA", "GAA", "SV%", "SO"]
    assert header == history.COLUMNS + ["penaltyMinutes", "timeOnIce"]
    assert schenn == ["20212022", "8474568", "Luke Schenn", "D", "VAN,TOR",
                      "80", "44", "79", "44", "1", "314", "318", "98",
                      *[""] * 12]
    assert mcdavid[-2:] == ["45", ""]
    assert goalie == ["20212022", "1", "No Shots", "G", "WPG", "66",
                      *[""] * 7, "66", "29", "27", "10", "2155", "1962",
                      "193", "", "", "4", "", "60"]


def test_stored_seasons_are_read_as_one_table(tmp_path):
    history.save_season_stats(2025, [
        {"season": 20242025, "player_id": 1, "name": "NA", "position": "D",
         "teams": "VAN,TOR", "GP": 70, "takeaways": 11}], tmp_path)
    history.save_season_stats(2026, [
        {"season": 20252026, "player_id": 1, "name": "NA", "position": "D",
         "teams": "TOR", "GP": 82, "plusMinus": -3},
        {"season": 20252026, "player_id": 2, "name": "Gus", "position": "G",
         "teams": "WPG", "GP": 60, "GAA": 2.4}], tmp_path)
    for other in ("season_20252026.part", "season_2026.csv",
                  "season_20252027.csv", "notes.csv"):
        (tmp_path / other).write_text("not a season")
    assert history.stored_seasons(tmp_path) == [2025, 2026]

    table = history.read_history(tmp_path)
    assert list(table.columns) == history.COLUMNS + ["takeaways", "plusMinus"]
    assert table[["season", "player_id", "name", "teams", "GP"]
                 ].values.tolist() == [
        [20242025, 1, "NA", "VAN,TOR", 70], [20252026, 1, "NA", "TOR", 82],
        [20252026, 2, "Gus", "WPG", 60]]
    assert table["takeaways"].tolist()[0] == 11
    assert table["takeaways"].isna().tolist() == [False, True, True]
    assert table["GAA"].isna().tolist() == [True, True, False]


def test_no_stored_seasons_are_an_empty_table(tmp_path):
    for folder in (tmp_path, tmp_path / "missing"):
        assert history.stored_seasons(folder) == []
        table = history.read_history(folder)
        assert table.empty and list(table.columns) == history.COLUMNS


@pytest.mark.parametrize("content, message", [
    ("", "cannot be read"), ("player,goals\nA,1\n", "is not a stored season")])
def test_a_file_that_is_no_season_is_refused(tmp_path, content, message):
    (tmp_path / "season_20252026.csv").write_text(content)
    with pytest.raises(history.NhlStatsError, match=message):
        history.read_history(tmp_path)


@pytest.fixture
def nhl(monkeypatch, tmp_path):
    """The command in an empty working directory, with the NHL stubbed."""
    monkeypatch.chdir(tmp_path)
    dates = Mock(return_value={**DATES, 2999: (date(2998, 10, 1),
                                               date(2999, 4, 10))})
    stats = Mock(side_effect=lambda year: [
        {"season": history.season_id(year), "position": "C"},
        {"season": history.season_id(year), "position": "G"}])
    monkeypatch.setattr(command, "fetch_season_dates", dates)
    monkeypatch.setattr(command, "fetch_season_stats", stats)
    return Mock(dates=dates, stats=stats, folder=tmp_path / "data" / "nhl")


def test_command_stores_each_selected_season(nhl, capsys):
    assert command.main(["2022", "2023", "2022"]) == 0
    assert sorted(p.name for p in nhl.folder.iterdir()) == [
        "season_20212022.csv", "season_20222023.csv"]
    assert [call.args for call in nhl.stats.call_args_list] == [
        (2022,), (2023,)]
    nhl.dates.assert_called_once_with()
    assert capsys.readouterr().out.splitlines() == [
        "2021-22: 1 skaters and 1 goalies -> data/nhl/season_20212022.csv",
        "2022-23: 1 skaters and 1 goalies -> data/nhl/season_20222023.csv"]


def test_command_keeps_a_stored_season_unless_refreshed(nhl, capsys):
    nhl.folder.mkdir(parents=True)
    stored = nhl.folder / "season_20212022.csv"
    stored.write_text("stored")
    assert command.main(["2022"]) == 0
    assert stored.read_text() == "stored"
    assert "already in" in capsys.readouterr().out
    nhl.dates.assert_not_called()
    nhl.stats.assert_not_called()
    assert command.main(["2022", "--refresh"]) == 0
    assert stored.read_text().startswith("season,player_id")


@pytest.mark.parametrize("year, message", [
    ("2999", "2998-99 totals are not final before 2999-04-12"),
    ("2024", "no season ending in 2024")])
def test_command_refuses_a_season_without_final_totals(nhl, capsys, year,
                                                       message):
    assert command.main(["2022", year, "2023"]) == 1
    assert message in capsys.readouterr().err
    assert [p.name for p in nhl.folder.iterdir()] == ["season_20212022.csv"]


def test_command_waits_a_day_after_the_last_games(nhl, capsys):
    yesterday = date.today() - timedelta(days=1)
    nhl.dates.return_value = {2022: (date(2021, 10, 12), yesterday)}
    assert command.main(["2022"]) == 1
    assert "not final before" in capsys.readouterr().err
    nhl.dates.return_value = {
        2022: (date(2021, 10, 12), yesterday - timedelta(days=1))}
    assert command.main(["2022"]) == 0


def test_command_reports_an_api_failure(nhl, capsys):
    nhl.stats.side_effect = history.NhlStatsError("The NHL is down.")
    assert command.main(["2022"]) == 1
    assert capsys.readouterr().err == "Error: The NHL is down.\n"
    assert not nhl.folder.exists()
