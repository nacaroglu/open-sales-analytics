from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.datasets import router as datasets_router
from app.config import get_settings
from app.errors import register_error_handlers


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Fail at startup, not on the first request, if the environment is invalid.
    get_settings()
    yield


app = FastAPI(title="Open Sales Analytics", lifespan=lifespan)
register_error_handlers(app)
app.include_router(datasets_router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
