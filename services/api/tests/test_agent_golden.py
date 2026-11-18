"""Agent grounding rules and evidence streaming, offline via FunctionModel (spec-08)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastmcp import FastMCP
from inversa.api.agent.orchestrator import build_toolset, read_freshness
from inversa.api.agent.prompts import SYSTEM_PROMPT
from inversa.api.chat import chat_events
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ToolCallPart
from pydantic_ai.models.function import DeltaToolCall, DeltaToolCalls, FunctionModel

TS: str = "2026-11-17T14:00:00Z"
START: str = "2026-11-17T13:00:00Z"
END: str = "2026-11-17T15:00:00Z"


def _model(first_call: ToolCallPart, final_text: str) -> FunctionModel:
    """Script a model: one tool call, then a grounded final answer."""
    state = {"called": False}

    async def run_model(
        messages: list[ModelMessage],
        info: Any,
    ) -> AsyncIterator[str | DeltaToolCalls]:
        if state["called"]:
            split = len(final_text) // 2 or 1
            yield final_text[:split]
            yield final_text[split:]
            return
        state["called"] = True
        yield {0: DeltaToolCall(name=first_call.tool_name, json_args=json.dumps(first_call.args))}

    return FunctionModel(stream_function=run_model)


async def _frames(stream: AsyncIterator[str]) -> list[tuple[str, dict[str, Any]]]:
    """Collect an SSE frame stream of the chat generator."""
    blocks = "".join([frame async for frame in stream]).strip().split("\n\n")
    frames: list[tuple[str, dict[str, Any]]] = []
    for block in blocks:
        event = data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                data = json.loads(line.removeprefix("data:").strip())
        if event is not None and data is not None:
            frames.append((event, data))
    return frames


def _run(agent: Agent[None, str], prompt: str) -> list[tuple[str, dict[str, Any]]]:
    return asyncio.run(_frames(chat_events(agent, prompt)))


def _grouped(frames: list[tuple[str, dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event, data in frames:
        grouped.setdefault(event, []).append(data)
    return grouped


def test_system_prompt_enforces_grounding_guardrails() -> None:
    """The persona text carries every spec-08 section 1 rule plus the output contract."""
    assert "~3 hours" in SYSTEM_PROMPT
    assert "never state a PM2.5 value" in SYSTEM_PROMPT
    assert "`stale`" in SYSTEM_PROMPT and "`outlier`" in SYSTEM_PROMPT
    assert "no active fires" in SYSTEM_PROMPT
    assert "boundary_layer_height" in SYSTEM_PROMPT
    assert "Output contract for every reply" in SYSTEM_PROMPT
    assert "at most 3 one-line evidence bullets" in SYSTEM_PROMPT
    assert "at most 2 one-line caveats" in SYSTEM_PROMPT
    assert "Never append a second bottom-line summary" in SYSTEM_PROMPT
    assert "under 120 words" in SYSTEM_PROMPT


def test_freshness_resource_is_readable(mcp_server: FastMCP) -> None:
    """resource://data/freshness backs the message context the route injects."""
    report = json.loads(asyncio.run(read_freshness(mcp_server)))
    assert isinstance(report, dict)


def test_causal_query_streams_tool_then_evidence_then_tokens(
    booted_engine: object, mcp_server: FastMCP
) -> None:
    """Golden prompt 1: analyze_downwind_impact evidence reaches the SSE stream."""
    model = _model(
        ToolCallPart(
            "analyze_downwind_impact",
            {"timestamp_iso": TS, "region_bbox": None, "radius_km": 150.0},
        ),
        "Downwind now: FIRE-1 feeds STA-DOWN readings.",
    )
    agent = Agent(model, instructions=SYSTEM_PROMPT, toolsets=[build_toolset(mcp_server)])
    grouped = _grouped(_run(agent, "Where is the smoke impacting air quality downwind?"))

    assert grouped["tool_call"] == [
        {"tool": "analyze_downwind_impact", "status": "running"}
    ]
    evidence = grouped["evidence"][0]
    assert {"FIRE-1"} <= set(evidence["fire_ids"])
    assert "STA-DOWN" in evidence["station_ids"]
    assert "focus_timestamp" in evidence
    text = "".join(data.get("text", "") for data in grouped["token"])
    assert "FIRE-1" in text


def test_station_attribution_streams_envelope(
    booted_engine: object, mcp_server: FastMCP
) -> None:
    """Golden prompt 3: the timeseries tool runs through the same evidence pipeline."""
    model = _model(
        ToolCallPart(
            "get_station_timeseries",
            {"station_id": "STA-DOWN", "start_iso": START, "end_iso": END},
        ),
        "Downslope Ridge spiked in sync with the plume.",
    )
    agent = Agent(model, instructions=SYSTEM_PROMPT, toolsets=[build_toolset(mcp_server)])
    grouped = _grouped(_run(agent, "Why did this station spike?"))

    assert grouped["tool_call"][0]["tool"] == "get_station_timeseries"
    assert grouped["token"]


def test_negative_case_reports_no_matches(booted_engine: object, mcp_server: FastMCP) -> None:
    """Golden prompt 5: an empty bbox region yields an explicit no-fire answer."""
    model = _model(
        ToolCallPart(
            "analyze_downwind_impact",
            {
                "timestamp_iso": TS,
                "region_bbox": [-121.0, 40.0, -120.0, 41.0],
                "radius_km": 150.0,
            },
        ),
        "No active fires north of you; check the boundary layer for stagnation.",
    )
    agent = Agent(model, instructions=SYSTEM_PROMPT, toolsets=[build_toolset(mcp_server)])
    grouped = _grouped(_run(agent, "Any fires affecting air quality in the north?"))

    assert grouped["tool_call"] == [{"tool": "analyze_downwind_impact", "status": "running"}]
    text = "".join(data.get("text", "") for data in grouped["token"])
    assert "No active fires" in text
