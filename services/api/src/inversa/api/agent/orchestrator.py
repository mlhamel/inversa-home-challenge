"""PydanticAI orchestrator wired to the mounted FastMCP surface (spec-05 section 2)."""

from __future__ import annotations

from typing import Any, Final

from fastmcp import Client, FastMCP
from inversa.api.agent.prompts import SYSTEM_PROMPT
from inversa.api.config import Settings
from pydantic_ai import FunctionToolset
from pydantic_ai.agent import Agent
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

FRESHNESS_URI: Final[str] = "resource://data/freshness"

TEST_MODEL_NAME: Final[str] = "test"


def build_toolset(mcp: FastMCP) -> FunctionToolset[Any]:
    """Expose the four FastMCP grounding tools as PydanticAI function tools.

    The wrappers shell out to the mounted MCP server so the agent consumes the
    exact same McpToolEnvelope payloads as any other MCP client (spec-04).
    """
    async def analyze_downwind_impact(
        timestamp_iso: str,
        region_bbox: list[float] | None = None,
        radius_km: float = 150.0,
    ) -> dict[str, Any]:
        """Correlate active fires -> wind -> downwind PM2.5 spikes at one instant.

        Args:
            timestamp_iso: ISO-8601 instant to analyze (naive values are UTC).
            region_bbox: optional [min_lon, min_lat, max_lon, max_lat] viewport.
            radius_km: station search radius around the wind corridor (default 150).
        """
        async with Client(mcp) as client:
            result = await client.call_tool(
                "analyze_downwind_impact",
                {
                    "timestamp_iso": timestamp_iso,
                    "region_bbox": region_bbox,
                    "radius_km": radius_km,
                },
            )
        return dict(result.data)

    async def get_station_timeseries(
        station_id: str,
        start_iso: str,
        end_iso: str,
    ) -> dict[str, Any]:
        """Fetch one station's hourly PM2.5 profile, wind vector, and nearby fires.

        Args:
            station_id: exact OpenAQ station identifier.
            start_iso: ISO-8601 window start (naive values are UTC).
            end_iso: ISO-8601 window end.
        """
        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_station_timeseries",
                {"station_id": station_id, "start_iso": start_iso, "end_iso": end_iso},
            )
        return dict(result.data)

    async def find_worst_air_quality_events(
        start_iso: str,
        end_iso: str,
        limit: int = 5,
    ) -> dict[str, Any]:
        """Rank the worst PM2.5 peaks over a window with exact timestamps.

        Args:
            start_iso: ISO-8601 window start (naive values are UTC).
            end_iso: ISO-8601 window end.
            limit: maximum number of per-station peak events (default 5).
        """
        async with Client(mcp) as client:
            result = await client.call_tool(
                "find_worst_air_quality_events",
                {"start_iso": start_iso, "end_iso": end_iso, "limit": limit},
            )
        return dict(result.data)

    async def list_active_fires(
        timestamp_iso: str,
        region_bbox: list[float] | None = None,
    ) -> dict[str, Any]:
        """List FIRMS active-fire detections in the trailing 4 h window at an instant.

        Args:
            timestamp_iso: ISO-8601 instant; naive values are treated as UTC.
            region_bbox: optional [min_lon, min_lat, max_lon, max_lat] viewport filter.
        """
        async with Client(mcp) as client:
            result = await client.call_tool(
                "list_active_fires",
                {"timestamp_iso": timestamp_iso, "region_bbox": region_bbox},
            )
        return dict(result.data)

    return FunctionToolset(
        [
            analyze_downwind_impact,
            get_station_timeseries,
            find_worst_air_quality_events,
            list_active_fires,
        ]
    )


def build_model(settings: Settings) -> Model | str:
    """Resolve the configured agent model; 'test' yields an offline TestModel."""
    if settings.agent_model == TEST_MODEL_NAME:
        from pydantic_ai.models.test import TestModel

        return TestModel(call_tools=[])
    if settings.agent_model.startswith("openai:") and settings.agent_base_url is not None:
        return OpenAIChatModel(
            settings.agent_model.removeprefix("openai:"),
            provider=OpenAIProvider(
                base_url=settings.agent_base_url,
                api_key=settings.agent_api_key or "unused",
            ),
        )
    return settings.agent_model


def build_agent(settings: Settings, mcp: FastMCP) -> Agent[None, str]:
    """Build the grounded chat agent over the FastMCP tool surface."""
    return Agent(
        build_model(settings),
        instructions=SYSTEM_PROMPT,
        toolsets=[build_toolset(mcp)],
    )


async def read_freshness(mcp: FastMCP) -> str:
    """Read resource://data/freshness verbatim for the chat prompt context."""
    async with Client(mcp) as client:
        blocks = await client.read_resource(FRESHNESS_URI)
    text = getattr(blocks[0], "text", None)
    return text if isinstance(text, str) else str(blocks[0])
