"""FastAPI bootstrap: engine lifespan, the /mcp mount (spec-04), and GET /health."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from inversa.api.chat import chat_router
from inversa.api.config import Settings, load_settings
from inversa.api.db.engine import close_engine, initialize_engine
from inversa.api.mcp.server import build_mcp
from inversa.api.rest import router as rest_router
from pydantic import BaseModel, ConfigDict
from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

APP_VERSION: str = "0.1.0"


class HealthResponse(BaseModel):
    """Liveness payload served at GET /health."""
    model_config = ConfigDict(frozen=True)

    status: str


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the API app: REST state endpoints, the /mcp mount, the agent, and /health.

    The DuckDB engine boots with the lifespan; `/api/*` serves map and timeline
    state, `/mcp` serves the FastMCP tool surface, `/api/chat` streams the
    PydanticAI agent as Server-Sent Events (Phase 4, spec-05), and GET /health
    answers liveness without touching any analytical surface.
    """
    resolved = settings or load_settings()
    mcp = build_mcp(resolved)
    mcp_app = mcp.http_app(path="/")

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        initialize_engine(resolved)
        stack = AsyncExitStack()
        try:
            await stack.enter_async_context(mcp_app.lifespan(mcp_app))
            yield
        finally:
            await stack.aclose()
            close_engine()

    app = FastAPI(title="Inversa Geo Explorer API", version=APP_VERSION, lifespan=lifespan)
    app.add_middleware(_StreamingSafeGzip)
    app.include_router(rest_router)
    app.include_router(chat_router(mcp, resolved))

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    app.mount("/mcp", mcp_app)
    return app


class _StreamingSafeGzip:
    """GZip-compress responses except the chat SSE stream.

    Compressing ``text/event-stream`` buffers token deltas inside the gzip
    window and delays streaming output, so ``/api/chat`` bypasses compression
    and everything else (37 KiB JSON snapshots included) shrinks on the wire.
    """

    def __init__(self, app: ASGIApp, minimum_size: int = 1024) -> None:
        self._app = app
        self._gzip = GZipMiddleware(app, minimum_size=minimum_size)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and str(scope.get("path", "")).startswith("/api/chat"):
            await self._app(scope, receive, send)
        else:
            await self._gzip(scope, receive, send)
