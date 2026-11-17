---
id: spec-06-frontend-timeline-map
title: Next.js Web Interface, Interactive Map, and Timeline
version: 1.0.0
depends_on: [spec-05-fastapi-agent-gateway]
---

# 1. Layout & Core Components
- **Full-Screen Geospatial Canvas (`MapLibre GL JS` + `Deck.gl`):**
  - **Layer 1 (`ScatterplotLayer` / `HeatmapLayer`):** NASA FIRMS active fires sized by `frp` (radiative power).
  - **Layer 2 (`ScatterplotLayer` / `IconLayer`):** OpenAQ stations colored by PM2.5 AQI scale; stations with `quality_flag == 'stale'` rendered in muted gray with a dashed outline and staleness tooltip warning.
  - **Layer 3 (`IconLayer` directional arrows):** Open-Meteo wind vectors rotated by `wind_direction_10m` and scaled by `wind_speed_10m`.
  - **Evidence Highlighting (`highlightedIds`):** `fire_ids` and `station_ids` received via SSE `evidence` events display an animated pulse ring and open a side Evidence Inspector drawer.
- **Interactive Timeline (Bottom Dock):**
  - Background dual-axis sparkline (max PM2.5 line + fire count bars) powered by `/api/timeline/summary`.
  - Draggable hourly scrubber + Play/Pause button (advances 1 hour per 800ms) with 100ms debounced fetches to `/api/snapshot`.
  - Shaded "Satellite Latency Window" indicator on the trailing 3 hours highlighting potential NASA FIRMS reporting lag[cite: 1].
- **Natural-Language Assistant Panel (Right Drawer):**
  - Chat interface with curated starter prompts (*"Where is wildfire smoke degrading air quality right now?"*, *"Show me the worst PM2.5 spike over the past 3 days"*).
  - Inline clickable evidence chips inside AI responses to jump to referenced timestamps or stations.