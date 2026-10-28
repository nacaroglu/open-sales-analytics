import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.routing import Match, Route
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from app.api.customers import router as customers_router
from app.api.datasets import router as datasets_router
from app.api.overview import router as overview_router
from app.api.products import router as products_router
from app.cleanup import prepare_dataset_dir, run_cleanup_loop, run_sweep_safely
from app.config import Settings, get_settings
from app.custom_metrics import use_custom_metrics
from app.domain_telemetry import use_tracer_provider
from app.errors import register_error_handlers
from app.health import readiness_checks
from app.http_instrumentation import RequestTelemetryMiddleware, configure_trace_context_propagation
from app.logging_config import RequestLogMiddleware, configure_logging
from app.telemetry import TelemetryProviders, create_telemetry


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    application.state.initialized = False
    timer: asyncio.Task | None = None
    telemetry: TelemetryProviders | None = None
    try:
        # Fail at startup, not on the first request, if the environment is invalid.
        settings = get_settings()
        telemetry = create_telemetry(settings)
        application.state.telemetry = telemetry
        assert telemetry.custom_metrics is not None
        with (
            use_custom_metrics(telemetry.custom_metrics),
            use_tracer_provider(telemetry.tracer_provider),
        ):
            prepare_dataset_dir(settings)
            await run_sweep_safely(settings)
            timer = asyncio.create_task(run_cleanup_loop(settings))
            application.state.initialized = True
            yield
    finally:
        application.state.initialized = False
        if timer is not None:
            timer.cancel()
            with suppress(asyncio.CancelledError):
                await timer
        if telemetry is not None:
            telemetry.shutdown()
        application.state.telemetry = None


configure_logging()
configure_trace_context_propagation()
# FastAPI's built-in telemetry records raw url.path/query values; use the scoped,
# privacy-safe middleware below as the single server instrumentation layer.
app = FastAPI(
    title="Open Sales Analytics",
    lifespan=lifespan,
    telemetry={"tracing": False, "metrics": False, "logs": False, "operation_spans": False},
)
app.state.initialized = False
app.add_middleware(RequestLogMiddleware)
app.add_middleware(RequestTelemetryMiddleware)
register_error_handlers(app)
app.include_router(datasets_router)
app.include_router(customers_router)
app.include_router(overview_router)
app.include_router(products_router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/live")
def health_live() -> dict[str, str]:
    """Report process responsiveness without checking downstream dependencies."""
    return {"status": "live"}


@app.get("/health/ready")
def health_ready(request: Request) -> JSONResponse:
    """Report readiness using only safe service identity and a generic failure body."""
    if not getattr(request.app.state, "initialized", False):
        return JSONResponse({"status": "not_ready"}, status_code=503)

    try:
        settings = get_settings()
        ready = readiness_checks(settings)
    except Exception:
        ready = False
    if not ready:
        return JSONResponse({"status": "not_ready"}, status_code=503)

    return JSONResponse(
        {
            "status": "ready",
            "service": "open-sales-analytics",
            "environment": settings.osa_environment,
            "version": settings.osa_version,
        },
        headers={"Cache-Control": "no-store"},
    )


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
