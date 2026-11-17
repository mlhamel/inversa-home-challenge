---
id: spec-08-agent-behavior-and-evals
title: AI Agent System Prompt, Grounding Guardrails, and Demo Scenarios
version: 1.0.0
depends_on: [spec-04-mcp-server-spec, spec-05-fastapi-agent-gateway]
---

# 1. Agent Persona & Grounding Rules (`services/api/src/agent/prompts.py`)
The `PydanticAI` orchestrator must enforce the following operational rules:
1. **Freshness First:** Whenever a user asks about "now", "today", "current", or "latest" conditions, the agent MUST read `resource://data/freshness` first and explicitly state the ~3-hour satellite latency on NASA FIRMS if discussing recent fires[cite: 1].
2. **Zero Uncited Claims:** Never state a PM2.5 value, fire count, or wind speed without calling an MCP tool first. Every numeric claim must map to a station name, fire ID, or timestamp returned in `McpToolEnvelope`.
3. **Explicit Handling of Imperfect Data:**
   - If `data_quality_notes` includes `'stale'` stations (>2h old) or `'outlier'` readings, explicitly warn the user (e.g., *"Station X is downwind but has not reported in 4 hours, creating a visibility gap"*).
   - If no active fires exist in the requested window/region, clearly state that and check whether elevated PM2.5 is caused by non-fire urban/weather conditions (e.g., low `boundary_layer_height` trapping pollutants).
4. **Proactive Timeline Navigation:** Always populate `evidence_refs.focus_timestamp` and `evidence_refs.bbox_focus` when referencing a specific event so the frontend map and timeline automatically jump to the evidence[cite: 1].

# 2. Golden Demo Prompts (Verification & UI Starter Chips)
Antigravity must verify that the agent handles these 5 canonical queries end-to-end:
1. **Causal Downwind Query:** *"Where is wildfire smoke currently impacting air quality downwind, and how reliable is the sensor coverage?"*
2. **Historical Peak Discovery:** *"What was the worst PM2.5 spike over the past 7 days, and can you show it on the timeline?"*
3. **Station-Specific Attribution:** *"Why did PM2.5 spike at [Station Name] yesterday afternoon? Was it wind-driven smoke or stagnant air?"*
4. **Data Quality / Stale Sensor Probe:** *"Are there any downwind monitoring stations near active fires that are currently offline or reporting stale data?"*
5. **Counterfactual / Negative Case:** *"Check the northern sector of the map—are any fires affecting air quality there right now?"*
