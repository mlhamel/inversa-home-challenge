"""Conversational SSE gateway over the PydanticAI agent (spec-05 section 2)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Final

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from fastmcp import FastMCP
from inversa.api.agent.orchestrator import build_agent, read_freshness
from inversa.api.config import Settings
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.agent import Agent
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
)

SSE_MEDIA_TYPE: Final[str] = "text/event-stream"


class ChatRequest(BaseModel):
    """One user message for the conversational endpoint."""

    model_config = ConfigDict(frozen=True)

    message: str = Field(min_length=1)


async def chat_events(agent: Agent[None, str], user_prompt: str) -> AsyncIterator[str]:
    """Stream the agent run as tool_call, thinking, evidence, and token SSE events."""
    try:
        async with agent.iter(user_prompt) as run:
            async for node in run:
                if Agent.is_call_tools_node(node):
                    async with node.stream(run.ctx) as tool_stream:
                        async for tool_event in tool_stream:
                            if isinstance(tool_event, FunctionToolCallEvent):
                                yield _sse(
                                    "tool_call",
                                    {"tool": tool_event.part.tool_name, "status": "running"},
                                )
                            elif isinstance(tool_event, FunctionToolResultEvent):
                                evidence = _extract_evidence(tool_event.part.content)
                                if evidence is not None:
                                    yield _sse("evidence", evidence)
                elif Agent.is_model_request_node(node):
                    async with node.stream(run.ctx) as text_stream:
                        async for event in text_stream:
                            if isinstance(event, PartStartEvent):
                                if isinstance(event.part, ThinkingPart) and event.part.content:
                                    yield _sse("thinking", {"text": event.part.content})
                                elif isinstance(event.part, TextPart) and event.part.content:
                                    yield _sse("token", {"text": event.part.content})
                            elif isinstance(event, PartDeltaEvent):
                                if (
                                    isinstance(event.delta, ThinkingPartDelta)
                                    and event.delta.content_delta
                                ):
                                    yield _sse(
                                        "thinking", {"text": event.delta.content_delta}
                                    )
                                elif (
                                    isinstance(event.delta, TextPartDelta)
                                    and event.delta.content_delta
                                ):
                                    yield _sse("token", {"text": event.delta.content_delta})
    except Exception:
        yield _sse("error", {"message": "The agent run failed mid-stream."})
        raise


def chat_router(mcp: FastMCP, settings: Settings) -> APIRouter:
    """Build the chat router bound to this app's MCP surface and settings."""
    router = APIRouter(prefix="/api", tags=["chat"])

    @router.post("/chat")
    async def chat(body: ChatRequest) -> StreamingResponse:
        """Answer one question with a grounded agent run streamed as SSE."""
        agent = build_agent(settings, mcp)
        freshness = await read_freshness(mcp)
        prompt = f"[Data freshness context]\n{freshness}\n\nUser question:\n{body.message}"
        return StreamingResponse(
            chat_events(agent, prompt),
            media_type=SSE_MEDIA_TYPE,
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router


def _sse(event: str, data: dict[str, Any]) -> str:
    """Encode one Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(data, separators=(",", ":"))}\n\n"


def _extract_evidence(content: Any) -> dict[str, Any] | None:
    """Pull the evidence refs (plus bbox focus) out of an McpToolEnvelope."""
    if not isinstance(content, dict):
        return None
    refs = content.get("evidence_refs")
    if not isinstance(refs, dict):
        return None
    evidence: dict[str, Any] = dict(refs)
    bbox = content.get("bbox_focus")
    if bbox is not None:
        evidence["bbox_focus"] = bbox
    return evidence
