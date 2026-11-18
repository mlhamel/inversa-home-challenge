# apps/web

Next.js (App Router) frontend for the wildfire & air-quality explorer.

**Current state:** holds the buf-generated TypeScript bindings under `src/generated/inversa/v1/` (Phase 1 codegen verification) — the application itself is *planned, Phase 5*.

Planned per the specs: MapLibre GL JS / Deck.gl map canvas, 60fps timeline scrubber, and a chat drawer with automatic evidence highlighting — fires and sensors lit up on the map from `EvidenceRefs` and the timeline scrubbed to the `focus_timestamp` of every agent answer.

TypeScript bindings under `src/generated/` are buf-owned; regenerate via `make proto`, never edit by hand.

Governing specs: [`specs/06-frontend-timeline-map.md`](../../specs/06-frontend-timeline-map.md), [`specs/01-data-contracts.md`](../../specs/01-data-contracts.md)
