"""The web backend: a local FastAPI app serving the views as JSON."""
import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ..config import LeagueConfig, load_config
from .routes import LOCAL_HOSTS, router
from .state import LeagueStore, UpstreamError

HOST = "127.0.0.1"
PORT = 8000
# the frontend of a source checkout and its build (npm run build in web/)
WEB = Path(__file__).resolve().parents[3] / "web"
WEB_DIST = WEB / "dist"
BUILD_HINT = "cd web && npm install && npm run build"

log = logging.getLogger(__name__)


def _build_is_outdated() -> bool:
    """Whether the frontend's sources changed after it was built."""
    sources = [WEB / "index.html", WEB / "package.json",
               *(WEB / "src").rglob("*")]
    built = (WEB_DIST / "index.html").stat().st_mtime
    return any(path.stat().st_mtime > built for path in sources
               if path.is_file())


def create_app(leagues: list[LeagueConfig] | None = None) -> FastAPI:
    """
    :param leagues: the leagues to serve (default: those of config.yaml)
    """
    app = FastAPI(title="fantasyNHL", docs_url="/api/docs", redoc_url=None,
                  openapi_url="/api/openapi.json")
    app.state.store = LeagueStore(load_config() if leagues is None
                                  else leagues)
    # a page of another site can reach a local server through DNS rebinding
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(LOCAL_HOSTS))
    app.include_router(router)

    @app.exception_handler(UpstreamError)
    def upstream_failed(request: Request, error: UpstreamError) -> JSONResponse:
        return JSONResponse(
            {"detail": f"The request to ESPN failed ({error})."},
            status_code=502)

    if (WEB_DIST / "index.html").is_file():
        if _build_is_outdated():
            log.warning("The built frontend is older than web/src; rebuild "
                        "it with: %s", BUILD_HINT)
        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
    else:
        log.warning("The frontend is not built, only the API is served; "
                    "build it with: %s", BUILD_HINT)

        @app.get("/", include_in_schema=False)
        def not_built() -> PlainTextResponse:
            return PlainTextResponse(
                "The fantasyNHL frontend is not built yet. In the "
                f"repository, run:\n\n    {BUILD_HINT}\n\nand restart the "
                "server. The API is described at /api/docs.\n")
    return app


def main() -> None:
    uvicorn.run(create_app(), host=HOST, port=PORT)
