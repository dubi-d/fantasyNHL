"""The HTTP API on the synthetic league: what it serves equals what the
terminal shows (the golden transcripts), and it stays local and tidy."""
import json
import logging
import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from fantasy_nhl.api import app as app_module
from fantasy_nhl.api import create_app, figures, state
from support import FakeLeague, finished, midseason, patch_everywhere, pre_draft

GOLDEN_DIR = Path(__file__).parent / "golden"
OPENAPI = Path(__file__).parents[1] / "web" / "openapi.json"
BASE = "/api/leagues/test-league"
STREAMERS = "streamers=102&streamers=108"  # Alpha C2 and Alpha D3
VIEWS = [
    "/weekly/scores", "/weekly/awards", "/weekly/awards?week=2",
    "/standings/accumulated", "/standings/luck", "/standings/power-rankings",
    "/standings/power-rankings?window=2", "/standings/category-profile",
    "/preview", "/preview?week=2&stats=season", "/preview?week=7",
    "/streaming/plan?team=0", f"/streaming/plan?team=0&{STREAMERS}",
    "/streaming/plan?team=0&week=2", "/streaming/plan?team=0&week=2&simulate=10",
    "/streaming/candidates?team=0", "/streaming/candidates?team=3&stats=season",
    "/schedule/outlook", "/schedule/outlook?scope=remaining&fit_team=0",
    "/schedule/outlook?scope=remaining&sort=Reg Score next 4",
    "/schedule/outlook?scope=playoffs&fit_team=1",
    "/review/leaders",
    "/review/leaders?scope=team&team=0&group=FD&sort=HIT&cells=rate",
    "/review/leaders?group=G&sort=SV%25&cells=total&stats=season",
    "/review/compare?players=101&players=102",
    "/review/origins", "/review/outlook", "/review/outlook?source=draft",
    "/review/draft-grades", "/review/draft-return", "/review/pickups",
    "/review/trades", "/review/team?team=1", "/review/team?team=1&source=draft",
    "/review/gaps?team=2",
]
INVALID = [
    "/weekly/awards?week=5", "/weekly/awards?week=0",
    "/standings/power-rankings?window=1", "/standings/power-rankings?window=0",
    "/preview?week=99", "/preview?week=0", "/preview?stats=projected",
    "/streaming/plan", "/streaming/plan?team=9",
    "/streaming/plan?team=0&streamers=Nobody",
    "/streaming/plan?team=0&streamers=401",  # on another roster
    "/streaming/plan?team=0&week=2&simulate=99",
    "/streaming/plan?team=0&simulate=31",  # the matchup is not over
    "/schedule/outlook?scope=past", "/schedule/outlook?playoff_weight=2",
    "/schedule/outlook?scope=remaining&sort=Luck", "/schedule/outlook?fit_team=x",
    "/schedule/outlook?fit_team=0",  # no Fit in the full scope
    "/schedule/outlook?scope=remaining&fit_team=7",
    "/review/leaders?scope=team", "/review/leaders?sort=Luck",
    "/review/leaders?group=G&sort=Spec", "/review/leaders?cells=total",
    "/review/compare?players=101", "/review/compare?players=101&players=109",
    "/review/compare?players=101&players=1", "/review/team?team=7",
]
# a view of every kind of figure
FIGURES = {
    "power_rankings": "/standings/power-rankings?window=3",
    "schedule_heatmap": "/schedule/outlook?scope=remaining",
    "schedule_combined": "/schedule/outlook?scope=playoffs",
    "level_spec": "/review/leaders",
    "category_radar": "/review/compare?players=101&players=102",
}


def _serve(monkeypatch, league: FakeLeague) -> SimpleNamespace:
    """A client of the app serving ``league``; ``calls`` counts fetches."""
    calls: dict[str, int] = {}
    saved = []

    def counted(name, fetch):
        def call(*args):
            calls[name] = calls.get(name, 0) + 1
            return fetch(*args)
        return call

    for name in FakeLeague.FETCHERS:
        patch_everywhere(monkeypatch, name, counted(name, getattr(league, name)))
    patch_everywhere(monkeypatch, "fetch_league_data",
                     counted("fetch_league_data", lambda config: league.data))
    patch_everywhere(monkeypatch, "save_calibration",
                     lambda name, calibration: saved.append((name, calibration)))
    client = TestClient(create_app(league.sources),
                        base_url="http://127.0.0.1")
    return SimpleNamespace(client=client, league=league, calls=calls,
                           saved=saved)


@pytest.fixture
def api(monkeypatch):
    return _serve(monkeypatch, midseason())


@pytest.fixture
def finished_api(monkeypatch):
    return _serve(monkeypatch, finished())


def _tables(view: dict) -> list[list[list[str]]]:
    """Every table of a served view as rows of cell texts (label first)."""
    return [[[row["label"]] + [cell["text"] for cell in row["cells"]]
             for row in block["rows"] + block["footer"]]
            for block in view["blocks"] if block["type"] == "table"]


def _golden_tables(case: str) -> list[list[list[str]]]:
    """The tables of a terminal transcript, in the same shape."""
    text = (GOLDEN_DIR / f"{case}.txt").read_text(encoding="utf-8")
    tables, rows = [], None
    for line in re.sub(r"␛\[[0-9;]*m", "", text).splitlines():
        if line.startswith("┏"):
            rows = []
        elif line.startswith("└"):
            tables.append(rows)
        elif line.startswith("│"):
            rows.append([cell.strip() for cell in line.strip()[1:-1].split("│")])
    return tables


@pytest.mark.parametrize("path", VIEWS)
def test_views_are_served(api, path):
    response = api.client.get(BASE + path)
    assert response.status_code == 200, response.text
    assert response.json()["blocks"]
    assert not re.search(r"swid|espn_s2|\{SWID\}", response.text, re.I)


@pytest.mark.parametrize("path", INVALID)
def test_invalid_parameters_are_refused(api, path):
    assert api.client.get(BASE + path).status_code == 422


@pytest.mark.parametrize("case,first,paths", [
    ("standings", 0, ["/standings/accumulated", "/standings/luck",
                      "/standings/category-profile"]),
    ("weekly_scores", 0, ["/weekly/scores"]),
    ("weekly_awards", 0, ["/weekly/awards?week=4"]),
    ("power_rankings", 0, ["/standings/power-rankings?window=3"]),
    ("preview", 0, ["/preview?week=5", "/preview?week=2", "/preview?week=6"]),
    ("preview_season_only", 0, ["/preview?week=5&stats=season"]),
    ("schedule", 0, ["/schedule/outlook?scope=full&playoff_weight=0.4",
                     "/schedule/outlook?scope=remaining&playoff_weight=0.25"
                     "&sort=Reg Score next 4",
                     "/schedule/outlook?scope=playoffs"]),
    ("review_leaders", 0, ["/review/leaders?group=F&sort=Score&cells=pct",
                           "/review/leaders?scope=fa&group=G&sort=Elite"
                           "&cells=rate"]),
    ("review_league", 0, ["/review/origins", "/review/outlook?source=draft",
                          "/review/outlook", "/review/pickups",
                          "/review/trades"]),
    ("review_draft", 0, ["/review/draft-grades", "/review/draft-return"]),
    ("review_team", 0, ["/review/team?team=1&source=draft",
                        "/review/team?team=1", "/review/gaps?team=2"]),
    ("planner", 0, [f"/streaming/plan?team=0&week=5&{STREAMERS}"]),
])
def test_tables_equal_the_terminal(api, case, first, paths):
    served = [table for path in paths
              for table in _tables(api.client.get(BASE + path).json())]
    assert served == _golden_tables(case)[first:first + len(served)]


def test_candidates_equal_the_terminal_pages(api):
    served = _tables(api.client.get(
        f"{BASE}/streaming/candidates?team=0&week=5&{STREAMERS}").json())
    pages = _golden_tables("planner")[3:6]
    assert served == [[row for page in pages for row in page]]


def test_players_can_be_reviewed_before_the_draft(monkeypatch):
    """Free agents alone make a pool; the roster views say what is missing."""
    client = _serve(monkeypatch, pre_draft()).client
    assert _tables(client.get(BASE + "/review/leaders?scope=fa").json()) == (
        _golden_tables("review_pre_draft")[:1])
    options = client.get(BASE + "/review/options").json()
    assert options["players"] and not options["drafted"]
    for path, text in (("/review/origins", "All rosters are empty."),
                       ("/review/team?team=0", "Alpha has an empty roster."),
                       ("/review/draft-grades",
                        "The league has not drafted yet.")):
        (block,) = client.get(BASE + path).json()["blocks"]
        assert block["spans"][0]["text"] == text


def test_remaining_schedule_of_playoffs_only(finished_api):
    """Nothing to blend once only playoff matchups remain."""
    url = BASE + "/schedule/outlook?scope=remaining"
    plain = finished_api.client.get(url).json()
    fitted = finished_api.client.get(url + "&fit_team=0").json()
    assert _tables(plain) + _tables(fitted) == (
        _golden_tables("schedule_finished")[2:4])
    assert plain["meta"] == {"sorts": [], "blends_playoffs": False}
    assert fitted["meta"]["sorts"] == ["Fit next 1"]
    columns = [column["name"] for column in plain["blocks"][0]["columns"]]
    assert "PO Score" in columns
    assert not {"Combined rest of season", "Reg Score next 1"} & set(columns)


def test_compared_namesakes_keep_their_columns(api):
    players = api.client.get(BASE + "/review/options").json()["players"]
    twins = [player["id"] for player in players
             if player["label"].startswith("Twin (")]
    assert len(twins) == 3
    view = api.client.get(BASE + "/review/compare?" + "&".join(
        f"players={pid}" for pid in twins)).json()
    columns = [column["name"] for column in view["blocks"][0]["columns"]]
    assert columns == ["Cat", "Twin (Bravo)", "Twin (FA)", "Twin (FA) #908"]


def test_leagues_and_meta(api):
    assert api.client.get("/api/leagues").json() == [
        {"id": "old-league", "name": "Old League", "year": 2026,
         "default": False},
        {"id": "test-league", "name": "Test League", "year": 2027,
         "default": True}]
    meta = api.client.get(BASE).json()
    assert meta["teams"] == ["Alpha", "Bravo", "Charlie", "Delta"]
    assert (meta["current_week"], meta["completed_matchups"]) == (5, 4)
    assert meta["weeks"][4] == {"week": 5, "completed": False,
                                "label": "Matchup 5 (Nov 2 – Nov 8) (current)"}
    assert meta["weeks"][6]["label"].endswith("(playoffs)")
    assert meta["categories"][4] == {"name": "GAA", "inverted": True}
    assert meta["calibration"] is None
    assert meta["warnings"] == []
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+[+-]\d\d:\d\d",
                        meta["loaded_at"])
    assert api.client.get("/api/leagues/nope").status_code == 404


def test_a_league_loads_without_the_calendar(api, monkeypatch):
    def fail(data):
        raise RuntimeError("calendar gone")
    patch_everywhere(monkeypatch, "fetch_week_dates", fail)
    meta = api.client.get(BASE).json()
    assert meta["weeks"][4]["label"] == "Matchup 5 (current)"
    assert meta["warnings"] == [
        "ESPN's calendar could not be read: matchups have no dates."]
    assert api.client.get(BASE + "/weekly/awards").status_code == 200
    assert api.client.get(BASE + "/standings/luck").status_code == 200


def test_columns_are_keyed_and_typed(api):
    table = api.client.get(BASE + "/standings/luck").json()["blocks"][0]
    columns = {column["key"]: column for column in table["columns"]}
    assert list(columns) == [c["name"] for c in table["columns"]]
    assert columns["Player"]["type"] == "text"
    assert {columns[key]["type"] for key in ("W", "Pts", "xPts", "Luck")} == {
        "number"}
    wins = table["rows"][0]["cells"][list(columns).index("W")]
    assert wins["value"] == 2 and wins["text"] == "2"
    # cells of a planner grid are marks, also where they look like numbers
    plan = api.client.get(BASE + "/streaming/plan?team=0").json()["blocks"]
    grid = next(block for block in plan if block["type"] == "table")
    assert {column["type"] for column in grid["columns"]} == {"text"}


def test_whole_numbers_stay_whole(api):
    curve = api.client.post(BASE + "/schedule/calibration", json={
        "source": "old-league"}).json()["blocks"][0]
    assert _tables({"blocks": [curve]})[0][0] == ["1", "4", "3.0", "7"]
    assert curve["rows"][0]["cells"][0]["value"] == 4


def test_review_options(api):
    options = api.client.get(BASE + "/review/options").json()
    assert options["drafted"]
    assert {"id": 908, "label": "Twin (C, FA) #908", "goalie": False} in (
        options["players"])
    sorts = {group["key"]: group["sorts"] for group in options["groups"]}
    assert sorts["F"] == ["Score", "Spec", "Elite", "G", "A", "PPP", "HIT"]
    assert sorts["G"] == ["Score", "Elite", "GAA", "SV%"]
    assert [c["key"] for c in options["cells"]] == ["pct", "rate"]
    season = api.client.get(BASE + "/review/options?stats=season").json()
    assert [c["key"] for c in season["cells"]] == ["pct", "rate", "total"]


def test_planner_meta_feeds_the_form(api):
    meta = api.client.get(BASE + "/streaming/plan?team=0").json()["meta"]
    assert meta["roster"][:2] == [{"id": 101, "name": "Alpha C1"},
                                  {"id": 102, "name": "Alpha C2"}]
    assert meta["has_open_days"] and not meta["finished"]
    past = api.client.get(BASE + "/streaming/plan?team=0&week=2").json()["meta"]
    assert past["finished"] and not past["has_open_days"]
    assert past["days"][0] == {"period": 8, "label": "Mon 12"}
    # views without choices of their own carry no meta
    assert "meta" not in api.client.get(BASE + "/standings/luck").json()


def test_streamers_are_told_apart_by_id(monkeypatch):
    league = midseason()
    league.review.rosters[0][2].name = "Alpha C2"  # a namesake of id 102
    client = _serve(monkeypatch, league).client
    plan = client.get(BASE + "/streaming/plan?team=0&streamers=102").json()
    grid = next(block for block in plan["blocks"] if block["type"] == "table")
    names = [row["cells"][0]["text"] for row in grid["rows"]]
    assert names.count("Alpha C2 *") == 1 and names.count("Alpha C2") == 1


@pytest.mark.parametrize("kind", FIGURES)
def test_every_kind_of_figure_is_drawn(api, kind):
    figure = api.client.get(BASE + FIGURES[kind]).json()["blocks"][-1]
    assert figure["type"] == "figure" and figure["kind"] == kind
    png = api.client.get(figure["url"])
    assert png.headers["content-type"] == "image/png"
    assert png.content.startswith(b"\x89PNG")
    assert "title" not in figure["data"] and figure["title"]


def test_figures(api, monkeypatch):
    path = BASE + "/standings/power-rankings"
    view = api.client.get(path + "?window=3").json()
    figure = view["blocks"][-1]
    mark = figure["url"].rsplit("v=", 1)[1]
    assert figure["url"] == f"{path}/figures/0.png?window=3&v={mark}"
    # the same content keeps its address, other content gets another
    assert api.client.get(path + "?window=3").json()["blocks"][-1] == figure
    other = api.client.get(path + "?window=2").json()["blocks"][-1]
    assert other["url"].rsplit("v=", 1)[1] != mark

    from fantasy_nhl import plots
    drawn = []
    render_png = plots.render_png
    monkeypatch.setattr(plots, "render_png", lambda kind, inputs: (
        drawn.append(kind), render_png(kind, inputs))[1])
    monkeypatch.setattr(figures, "_rendered", type(figures._rendered)())
    pinned = api.client.get(figure["url"])
    assert pinned.headers["cache-control"] == (
        "private, max-age=86400, immutable")
    plain = api.client.get(f"{path}/figures/0.png?window=3")
    assert plain.headers["cache-control"] == "private, no-cache"
    assert plain.content == pinned.content and drawn == ["power_rankings"]
    assert api.client.get(f"{path}/figures/0.png?window=3", headers={
        "if-none-match": plain.headers["etag"]}).status_code == 304
    assert api.client.get(f"{path}/figures/1.png").status_code == 404
    assert api.client.get(BASE + "/standings/luck/figures/0.png"
                          ).status_code == 404


def test_figures_carry_their_data(api):
    figure = api.client.get(
        BASE + "/schedule/outlook?scope=remaining").json()["blocks"][-1]
    data = figure["data"]
    games = data["games"]
    assert games["type"] == "frame" and games["columns"] == ["5", "6", "7", "8"]
    assert len(games["rows"]) == len(games["index"]) == 20
    assert data["playoff_weeks"] == [7, 8]
    scores = data["scores"]
    assert list(scores) == ["Combined rest of season", "Reg Score next 4",
                            "PO Score"]
    assert scores["PO Score"]["type"] == "series"
    assert scores["PO Score"]["index"] == games["index"]


def test_fetches_are_cached_until_reload(api):
    for _ in range(2):
        api.client.get(BASE + "/preview?week=5")
        api.client.get(BASE + "/streaming/plan?team=0&week=5")
    assert api.calls["fetch_preview_data"] == 1
    assert api.calls["fetch_league_data"] == 1
    assert api.client.post(BASE + "/reload", json={}).status_code == 200
    api.client.get(BASE + "/preview?week=5")
    assert api.calls["fetch_preview_data"] == 2
    assert api.calls["fetch_league_data"] == 2


def test_an_old_load_is_replaced(api, monkeypatch):
    first = api.client.get(BASE).json()["loaded_at"]
    api.client.get(BASE + "/preview?week=5")
    assert api.client.get(BASE).json()["loaded_at"] == first
    monkeypatch.setattr(state, "SESSION_SECONDS", 0)
    assert api.client.get(BASE).json()["loaded_at"] > first
    api.client.get(BASE + "/preview?week=5")
    assert api.calls["fetch_preview_data"] == 2  # nothing kept of the old one


def test_a_reload_starts_clean(api, monkeypatch):
    """What a request of the old load still fetches stays with that load."""
    entry = api.client.app.state.store.leagues["test-league"]
    old = entry.session()
    entry.reload()
    new = entry.session()
    assert new is not old and new.data is old.data  # the fake's one snapshot
    assert old.fetch(("key",), lambda: "stale") == "stale"
    assert new.fetch(("key",), lambda: "fresh") == "fresh"

    # derived values follow their source, expired fetches are dropped
    source = object()
    assert new.derived(("d",), source, lambda: 1) == 1
    assert new.derived(("d",), source, lambda: 2) == 1
    assert new.derived(("d",), object(), lambda: 3) == 3
    monkeypatch.setattr(state, "CACHE_SECONDS", 0)
    assert new.fetch(("other",), lambda: "x") == "x"
    assert list(new._cache) == [("other",)]


def test_only_local_json_requests_change_state(api):
    reload = BASE + "/reload"
    assert api.client.post(reload).status_code == 415
    assert api.client.post(reload, content="{}", headers={
        "content-type": "text/plain"}).status_code == 415
    assert api.client.post(reload, json={}, headers={
        "origin": "https://evil.example"}).status_code == 403
    assert api.client.post(reload, json={}, headers={
        "origin": "http://localhost:5173"}).status_code == 200
    assert api.client.get(BASE, headers={
        "host": "evil.example"}).status_code == 400


def test_calibration_is_previewed_then_stored(api):
    url = BASE + "/schedule/calibration"
    table = api.client.post(url, json={"source": "old-league"}).json()
    assert table["blocks"][0]["title"].startswith(
        "Night value curve from Old League")
    assert not api.saved
    assert api.client.post(url, json={"source": "nope"}).status_code == 422

    stored = api.client.put(url, json={"source": "old-league"}).json()
    assert stored["source"] == "Old League"
    (name, calibration), = api.saved
    assert name == "Test League" and calibration.curve
    assert api.client.get(BASE).json()["calibration"] == stored
    note = api.client.get(BASE + "/schedule/outlook").json()["blocks"][1]
    assert "calibrated on Old League" in note["spans"][0]["text"]


def test_espn_failures_are_reported_without_details(api, monkeypatch, caplog):
    cookie = api.league.config.espn_s2

    def fail(data, week):
        raise RuntimeError(f"espn_s2={cookie} rejected")
    patch_everywhere(monkeypatch, "fetch_preview_data", fail)
    with caplog.at_level(logging.ERROR):
        response = api.client.get(BASE + "/preview")
    assert response.status_code == 502
    assert response.json() == {
        "detail": "The request to ESPN failed (RuntimeError)."}
    # the log says where it failed, but not the message with the cookie
    assert "RuntimeError" in caplog.text and "in fail" in caplog.text
    assert f"={cookie}" not in caplog.text


def test_missing_frontend_build_is_explained(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(app_module, "WEB_DIST", tmp_path / "dist")
    with caplog.at_level(logging.WARNING):
        client = TestClient(create_app([]), base_url="http://127.0.0.1")
    assert "npm run build" in caplog.text
    page = client.get("/")
    assert page.status_code == 200 and "npm run build" in page.text
    assert client.get("/api/leagues").json() == []


def test_outdated_frontend_build_is_noticed(monkeypatch, tmp_path, caplog):
    web = tmp_path / "web"
    for name in ("dist/index.html", "src/main.tsx"):
        (web / name).parent.mkdir(parents=True)
        (web / name).write_text("")
    monkeypatch.setattr(app_module, "WEB", web)
    monkeypatch.setattr(app_module, "WEB_DIST", web / "dist")
    os.utime(web / "dist/index.html", (1000, 1000))
    with caplog.at_level(logging.WARNING):
        create_app([])
    assert "older than web/src" in caplog.text
    caplog.clear()
    os.utime(web / "src/main.tsx", (500, 500))
    with caplog.at_level(logging.WARNING):
        create_app([])
    assert not caplog.text


def test_committed_api_schema_is_current():
    """web/openapi.json is what the frontend's types are generated from."""
    schema = json.dumps(create_app([]).openapi(), indent=2,
                        sort_keys=True) + "\n"
    if os.environ.get("UPDATE_OPENAPI"):
        OPENAPI.write_text(schema)
    assert OPENAPI.read_text() == schema, (
        "The API changed: rerun this test with UPDATE_OPENAPI=1, then "
        "`npm run types` in web/")
