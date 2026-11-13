"""What the route modules share: the league dependencies, the guard for
state changes, parameter checks and the registration of views."""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from ...sources.espn import fetch_week_dates
from ...views.model import WARNING, FigureBlock, View, note
from ..figures import fingerprint, render
from ..serialize import serialize_view, view_model
from ..state import LeagueEntry, LeagueSession, UpstreamError

LEAGUE = "/leagues/{league}"
LOCAL_HOSTS = ("127.0.0.1", "localhost")

Stats = Literal["blended", "season"]


def get_entry(league: str, request: Request) -> LeagueEntry:
    entry = request.app.state.store.leagues.get(league)
    if entry is None:
        raise HTTPException(404, "Unknown league")
    return entry


Entry = Annotated[LeagueEntry, Depends(get_entry)]


def get_session(entry: Entry) -> LeagueSession:
    return entry.session()


Session = Annotated[LeagueSession, Depends(get_session)]


def local_write(request: Request) -> None:
    """Guard for state-changing requests: JSON only (a page of another
    site cannot send that without permission) and no foreign Origin."""
    content_type = request.headers.get("content-type", "")
    if content_type.split(";")[0].strip().lower() != "application/json":
        raise HTTPException(415, "Send application/json")
    origin = request.headers.get("origin")
    if origin and origin.split("://")[-1].split(":")[0] not in LOCAL_HOSTS:
        raise HTTPException(403, "Foreign origin")


def invalid(message: str) -> HTTPException:
    return HTTPException(422, message)


def in_range(value: int, low: int, high: int, name: str) -> int:
    if not low <= value <= high:
        raise invalid(f"{name} must be between {low} and {high}")
    return value


def team_row(session: LeagueSession, team: int, name: str = "team") -> int:
    return in_range(team, 0, len(session.data.team_names) - 1, name)


def warning(text: str) -> View:
    return View([note(text, level=WARNING)])


def total_weeks(session: LeagueSession) -> int:
    return session.data.total_weeks or session.data.current_week


def week_dates(session: LeagueSession) -> dict | None:
    """First and last day by matchup week; None when ESPN's calendar
    cannot be read (the league itself is still usable)."""
    data = session.data
    try:
        return session.fetch(("week_dates",), lambda: fetch_week_dates(data))
    except UpstreamError:
        return None


def view(router: APIRouter, path: str, meta: type[BaseModel] | None = None):
    """Register a function building a View from path and query parameters
    as a JSON endpoint, plus the PNG endpoint of its figures.

    :param meta: model of the view's ``meta`` (default: it has none)
    """
    model = view_model(meta)

    def register(build):
        def as_json(request: Request, built: View = Depends(build)):
            def figure_url(index: int, block: FigureBlock) -> str:
                # the content mark lets the browser keep the image for good
                query = "&".join(filter(None, (
                    request.url.query, f"v={fingerprint(block)}")))
                return f"{request.url.path}/figures/{index}.png?{query}"
            return serialize_view(built, figure_url, model)

        def as_png(figure: int, request: Request,
                   built: View = Depends(build)) -> Response:
            blocks = [block for block in built.blocks
                      if isinstance(block, FigureBlock)]
            if not 0 <= figure < len(blocks):
                raise HTTPException(404, "This view has no such figure")
            mark = fingerprint(blocks[figure])
            etag = f'"{mark}"'
            pinned = request.query_params.get("v") == mark
            headers = {"ETag": etag, "Cache-Control": (
                "private, max-age=86400, immutable" if pinned
                else "private, no-cache")}
            if request.headers.get("if-none-match") == etag:
                return Response(status_code=304, headers=headers)
            return Response(render(blocks[figure], mark),
                            media_type="image/png", headers=headers)

        router.add_api_route(LEAGUE + path, as_json, name=build.__name__,
                             response_model=model)
        router.add_api_route(f"{LEAGUE}{path}/figures/{{figure}}.png", as_png,
                             include_in_schema=False)
        return build
    return register
