"""Sync test helpers that exercise a FastMCP server in-process."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastmcp import Client, FastMCP


def call_tool(server: FastMCP, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Invoke one tool on an in-memory client and return the payload dictionary."""

    async def _invoke() -> dict[str, Any]:
        async with Client(server) as client:
            result = await client.call_tool(name, arguments)
            return dict(result.data)

    return asyncio.run(_invoke())


def read_resource(server: FastMCP, uri: str) -> dict[str, Any]:
    """Read one resource on an in-memory client and return the parsed JSON."""

    async def _read() -> dict[str, Any]:
        async with Client(server) as client:
            blocks = await client.read_resource(uri)
            payload: dict[str, Any] = json.loads(blocks[0].text)
            return payload

    return asyncio.run(_read())
