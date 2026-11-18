# syntax=docker/dockerfile:1
# Build context is the repository root:
#   docker build -f services/ingestion/Dockerfile -t inversa-ingestion .
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY packages/shared-schemas packages/shared-schemas
COPY services/api/pyproject.toml services/api/pyproject.toml
COPY services/ingestion/pyproject.toml services/ingestion/pyproject.toml

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --no-install-project --package inversa-ingestion

COPY services/ingestion/src services/ingestion/src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package inversa-ingestion

FROM python:3.12-slim-bookworm

RUN useradd --create-home --uid 1000 inversa

COPY --from=build --chown=inversa:inversa /app/.venv /app/.venv

USER inversa

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

CMD ["python", "-m", "inversa.ingestion.backfill"]
