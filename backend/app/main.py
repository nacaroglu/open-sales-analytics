import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.api.datasets import router as datasets_router
from app.cleanup import prepare_dataset_dir, run_cleanup_loop, run_sweep_safely
from app.config import get_settings
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
