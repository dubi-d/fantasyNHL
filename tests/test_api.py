"""The HTTP API on the synthetic league: what it serves equals what the
terminal shows (the golden transcripts), and it stays local and tidy."""
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from fantasy_nhl.api import create_app
from support import FakeLeague, patch_everywhere

GOLDEN_DIR = Path(__file__).parent / "golden"
BASE = "/api/leagues/test-league"
VIEWS = [
    "/weekly/scores", "/weekly/awards", "/weekly/awards?week=2",
    "/standings/accumulated", "/standings/luck", "/standings/power-rankings",
    "/standings/power-rankings?window=2", "/standings/category-profile",
    "/preview", "/preview?week=2&stats=season", "/preview?week=7",
    "/streaming/plan?team=0",
    "/streaming/plan?team=0&streamers=Alpha C2&streamers=Alpha D3",
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
    "/weekly/awards?week=5", "/standings/power-rankings?window=1",
    "/preview?week=99", "/preview?stats=projected", "/streaming/plan",
    "/streaming/plan?team=9", "/streaming/plan?team=0&streamers=Nobody",
    "/streaming/plan?team=0&week=2&simulate=99",
    "/schedule/outlook?scope=past", "/schedule/outlook?playoff_weight=2",
    "/schedule/outlook?scope=remaining&sort=Luck", "/schedule/outlook?fit_team=x",
    "/review/leaders?scope=team", "/review/leaders?sort=Luck",
    "/review/leaders?group=G&sort=Spec", "/review/leaders?cells=total",
    "/review/compare?players=101", "/review/compare?players=101&players=109",
    "/review/compare?players=101&players=1", "/review/team?team=7",
]


@pytest.fixture
def api(monkeypatch):
    """A client of the app serving a FakeLeague; ``calls`` counts fetches."""
    league = FakeLeague()
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
    ("planner", 0, ["/streaming/plan?team=0&week=5&streamers=Alpha C2"
                    "&streamers=Alpha D3"]),
])
def test_tables_equal_the_terminal(api, case, first, paths):
    served = [table for path in paths
              for table in _tables(api.client.get(BASE + path).json())]
    assert served == _golden_tables(case)[first:first + len(served)]


def test_candidates_equal_the_terminal_pages(api):
    served = _tables(api.client.get(
        BASE + "/streaming/candidates?team=0&week=5&streamers=Alpha C2"
        "&streamers=Alpha D3").json())
    pages = _golden_tables("planner")[3:6]
    assert served == [[row for page in pages for row in page]]


def test_leagues_and_meta(api):
    assert api.client.get("/api/leagues").json() == [
        {"id": "old-league", "name": "Old League", "year": 2026},
        {"id": "test-league", "name": "Test League", "year": 2027}]
    meta = api.client.get(BASE).json()
    assert meta["teams"] == ["Alpha", "Bravo", "Charlie", "Delta"]
    assert (meta["current_week"], meta["completed_matchups"]) == (5, 4)
    assert meta["weeks"][4] == {"week": 5, "completed": False,
                                "label": "Matchup 5 (Nov 2 – Nov 8) (current)"}
    assert meta["weeks"][6]["label"].endswith("(playoffs)")
    assert meta["categories"][4] == {"name": "GAA", "inverted": True}
    assert meta["calibration"] is None
    assert api.client.get("/api/leagues/nope").status_code == 404


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
    assert meta["roster"][:2] == ["Alpha C1", "Alpha C2"]
    assert meta["has_open_days"] and not meta["finished"]
    past = api.client.get(BASE + "/streaming/plan?team=0&week=2").json()["meta"]
    assert past["finished"] and not past["has_open_days"]
    assert past["days"][0] == {"period": 8, "label": "Mon 12"}


def test_figures(api):
    path = BASE + "/standings/power-rankings"
    view = api.client.get(path + "?window=3").json()
    figure = view["blocks"][-1]
    assert figure["type"] == "figure" and figure["kind"] == "power_rankings"
    assert figure["url"] == path + "/figure.png?window=3"
    png = api.client.get(figure["url"])
    assert png.headers["content-type"] == "image/png"
    assert png.content.startswith(b"\x89PNG")
    assert api.client.get(BASE + "/standings/luck/figure.png").status_code == 404


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


def test_espn_failures_are_reported_without_details(api, monkeypatch):
    def fail(data, week):
        raise RuntimeError("espn_s2=S2 rejected")
    patch_everywhere(monkeypatch, "fetch_preview_data", fail)
    response = api.client.get(BASE + "/preview")
    assert response.status_code == 502
    assert response.json() == {
        "detail": "The request to ESPN failed (RuntimeError)."}
