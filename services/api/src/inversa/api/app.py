"""FastAPI bootstrap: engine lifespan and the /mcp mount (spec-04 section 1)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from inversa.api.config import Settings, load_settings
from inversa.api.db.engine import close_engine, initialize_engine
from inversa.api.mcp.server import build_mcp

APP_VERSION: str = "0.1.0"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the API app, serving the FastMCP tool surface at /mcp.

    The app has no REST routes of its own: the DuckDB engine boots with the
    lifespan and every analytical interaction flows through the mounted MCP
    server (Phase 4 owns the agent gateway endpoints).
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
    app.mount("/mcp", mcp_app)
    return app
