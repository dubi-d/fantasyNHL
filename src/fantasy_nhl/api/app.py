"""The web backend: a local FastAPI app serving the views as JSON."""
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ..config import LeagueConfig, load_config
from .routes import LOCAL_HOSTS, router
from .state import LeagueStore, UpstreamError

HOST = "127.0.0.1"
PORT = 8000


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

    return app


def main() -> None:
    uvicorn.run(create_app(), host=HOST, port=PORT)
