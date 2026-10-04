# One image: FastAPI serves the API and the built React app from the same origin on port 8000.

# Stage 1: build the frontend (Node is not part of the final image).
FROM node:22 AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: build the virtual environment from uv.lock, without the dev group.
# `--locked` fails the build if uv.lock does not match pyproject.toml.
FROM python:3.12-slim AS backend-deps
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=0 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# Stage 3: runtime. Only the virtual environment, backend/app and the built frontend.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    DATASET_DIR=/data

# Non-root user. /data is created owned by it with private permissions (0700, as the README promises), so a named volume mounted at /data is
# writable. A host directory mounted at /data must be writable by this user (UID 10001).
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app \
    && mkdir /data \
    && chown app:app /data \
    && chmod 700 /data

WORKDIR /app
COPY --from=backend-deps /app/.venv /app/.venv
COPY backend/app /app/backend/app
COPY --from=frontend /build/frontend/dist /app/frontend/dist

USER 10001
EXPOSE 8000
VOLUME /data

# The slim image has no curl: use the standard library.
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"]

# Exec form: uvicorn is PID 1 and handles SIGTERM, so `docker stop` ends it quickly.
CMD ["uvicorn", "app.main:app", "--app-dir", "/app/backend", "--host", "0.0.0.0", "--port", "8000"]
