# syntax=docker/dockerfile:1
# Build context is the repository root:
#   docker build -f services/api/Dockerfile -t inversa-backend .
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY packages/shared-schemas packages/shared-schemas
COPY services/api/pyproject.toml services/api/pyproject.toml
COPY services/ingestion/pyproject.toml services/ingestion/pyproject.toml

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --no-install-project --package inversa-api

COPY services/api/src services/api/src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package inversa-api

FROM python:3.12-slim-bookworm

RUN useradd --create-home --uid 1000 inversa

COPY --from=build --chown=inversa:inversa /app/.venv /app/.venv

USER inversa

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn inversa.api.app:create_app --factory --host 0.0.0.0 --port ${PORT:-8080}"]
