"""The chat endpoint streams agent runs as Server-Sent Events (spec-05 section 2)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from inversa.api.agent import orchestrator
from inversa.api.app import create_app
from inversa.api.config import Settings
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model
from pydantic_ai.models.function import (
    DeltaThinkingCalls,
    DeltaThinkingPart,
    DeltaToolCall,
    DeltaToolCalls,
    FunctionModel,
)
from starlette.testclient import TestClient

GOLDEN_PROMPTS: list[str] = [
    (
        "Where is wildfire smoke currently impacting air quality downwind, and how"
        " reliable is the sensor coverage?"
    ),
    "What was the worst PM2.5 spike over the past 7 days, and can you show it on the timeline?",
    (
        "Why did PM2.5 spike at Downslope Ridge yesterday afternoon? Was it wind-driven"
        " smoke or stagnant air?"
    ),
    (
        "Are there any downwind monitoring stations near active fires that are currently"
        " offline or reporting stale data?"
    ),
    "Check the northern sector of the map—are any fires affecting air quality there right now?",
]

ANALYSIS_TS: str = "2026-11-17T14:00:00Z"


@pytest.fixture
def chat(api_settings: Settings) -> Iterator[TestClient]:
    """Serve the app with the offline test model (agent_model='test')."""
    app = create_app(api_settings.model_copy(update={"agent_model": "test"}))
    with TestClient(app) as client:
        yield client


def _frames(text: str) -> list[tuple[str, dict[str, Any]]]:
    """Parse an SSE body into (event, data) frames."""
    frames: list[tuple[str, dict[str, Any]]] = []
    for block in text.strip().split("\n\n"):
        event: str | None = None
        data: dict[str, Any] | None = None
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                data = json.loads(line.removeprefix("data:").strip())
        if event is not None and data is not None:
            frames.append((event, data))
    return frames


def test_chat_streams_tokens_over_event_stream(chat: TestClient) -> None:
    """POST /api/chat answers as text/event-stream with at least one token event."""
    response = chat.post("/api/chat", json={"message": GOLDEN_PROMPTS[0]})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = _frames(response.text)
    assert not any(event == "tool_call" for event, _ in frames)
    text = "".join(data.get("text", "") for event, data in frames if event == "token")
    assert text


@pytest.mark.parametrize("prompt", GOLDEN_PROMPTS, ids=range(1, 6))
def test_every_golden_prompt_completes(chat: TestClient, prompt: str) -> None:
    """All five spec-08 golden demo prompts run end-to-end over the gateway."""
    response = chat.post("/api/chat", json={"message": prompt})
    assert response.status_code == 200
    assert _frames(response.text)


def test_chat_rejects_an_empty_message(chat: TestClient) -> None:
    """The conversational endpoint validates the user message."""
    assert chat.post("/api/chat", json={"message": ""}).status_code == 422


def test_chat_streams_tool_and_evidence_events(
    chat: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A scripted tool run surfaces tool_call and evidence frames over the route."""

    state = {"called": False}

    async def run_model(
        messages: list[ModelMessage],
        info: Any,
    ) -> AsyncIterator[str | DeltaToolCalls]:
        if state["called"]:
            yield "Grounded analysis complete."
            return
        state["called"] = True
        yield {
            0: DeltaToolCall(
                name="analyze_downwind_impact",
                json_args=json.dumps({"timestamp_iso": ANALYSIS_TS}),
            )
        }

    def scripted_model(settings: Settings) -> Model | str:
        return FunctionModel(stream_function=run_model)

    monkeypatch.setattr(orchestrator, "build_model", scripted_model)
    response = chat.post("/api/chat", json={"message": "Any active fires right now?"})
    assert response.status_code == 200
    frames = _frames(response.text)
    tools = [data["tool"] for event, data in frames if event == "tool_call"]
    assert tools == ["analyze_downwind_impact"]
    evidence = [data for event, data in frames if event == "evidence"]
    assert evidence
    assert all("fire_ids" in data for data in evidence)
    assert any(data["fire_ids"] for data in evidence)
    tokens = "".join(data.get("text", "") for event, data in frames if event == "token")
    assert tokens == "Grounded analysis complete."


def test_chat_streams_thinking_events(
    chat: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A scripted reasoning stream surfaces thinking frames before the token answer."""

    async def run_model(
        messages: list[ModelMessage],
        info: Any,
    ) -> AsyncIterator[str | DeltaThinkingCalls]:
        yield {1: DeltaThinkingPart(content="")}  # empty start part: no SSE frame
        yield {0: DeltaThinkingPart(content="Check fresh fires and wind bearings. ")}
        yield {0: DeltaThinkingPart(content="Then match downwind stations.")}
        yield "Answer grounded in fresh data."

    def scripted_model(settings: Settings) -> Model | str:
        return FunctionModel(stream_function=run_model)

    monkeypatch.setattr(orchestrator, "build_model", scripted_model)
    response = chat.post("/api/chat", json={"message": "Any smoke headed my way?"})
    assert response.status_code == 200
    frames = _frames(response.text)
    thinking_events = [event for event, _ in frames]
    assert thinking_events == ["thinking", "thinking", "token"]
    thinking = "".join(data.get("text", "") for event, data in frames if event == "thinking")
    assert thinking == (
        "Check fresh fires and wind bearings. Then match downwind stations."
    )
    tokens = "".join(data.get("text", "") for event, data in frames if event == "token")
    assert tokens == "Answer grounded in fresh data."
