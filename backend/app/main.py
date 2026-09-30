import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse, JSONResponse
from starlette.routing import Match, Route
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from app.api.datasets import router as datasets_router
from app.cleanup import prepare_dataset_dir, run_cleanup_loop, run_sweep_safely
from app.config import Settings, get_settings
from app.errors import register_error_handlers
from app.logging_config import RequestLogMiddleware, configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Fail at startup, not on the first request, if the environment is invalid.
    settings = get_settings()
    prepare_dataset_dir(settings)
    await run_sweep_safely(settings)
    timer = asyncio.create_task(run_cleanup_loop(settings))
    try:
        yield
    finally:
        timer.cancel()
        with suppress(asyncio.CancelledError):
            await timer


configure_logging()
app = FastAPI(title="Open Sales Analytics", lifespan=lifespan)
app.add_middleware(RequestLogMiddleware)
register_error_handlers(app)
app.include_router(datasets_router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
def public_config(settings: Settings = Depends(get_settings)) -> JSONResponse:
    # Public on purpose: only what the upload screen needs, never a path, TTL or token.
    return JSONResponse(
        {
            "public_demo_mode": settings.public_demo_mode,
            "max_upload_bytes": settings.max_upload_bytes,
            "max_rows": settings.max_rows,
        },
        headers={"Cache-Control": "no-store"},
    )


class _SpaFallbackRoute(Route):
    """Matches every GET and HEAD path except the ``/api`` tree."""

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        path = scope["path"]
        if path == "/api" or path.startswith("/api/"):
            return Match.NONE, {}
        return super().matches(scope)


def mount_frontend(app: FastAPI, dist_dir: Path) -> None:
    """Serve the built React app from the same origin as the API.

    ``/assets`` comes from ``dist_dir/assets``; every other GET or HEAD outside ``/api``
    answers with ``dist_dir/index.html`` so a reloaded ``/d/<id>`` reaches the router.
    Nothing is read from a path built from the request. Call it after the API routes.
    """
    index = dist_dir / "index.html"

    async def spa_index(_: object) -> FileResponse:
        return FileResponse(index, media_type="text/html")

    app.mount("/assets", StaticFiles(directory=dist_dir / "assets"), name="assets")
    app.router.routes.append(_SpaFallbackRoute("/{path:path}", spa_index, methods=["GET", "HEAD"]))


# <repository root>/frontend/dist; in the image /app/frontend/dist next to /app/backend/app.
_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _FRONTEND_DIST.is_dir():
    mount_frontend(app, _FRONTEND_DIST)
