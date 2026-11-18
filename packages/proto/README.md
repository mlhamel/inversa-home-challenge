# packages/proto

Protobuf single source of truth for all Inversa contracts.

- [`inversa/v1/telemetry.proto`](inversa/v1/telemetry.proto) — the three live feeds as canonical records: `FireDetection`, `AirQualityReading`, `WindVector`, plus `FireConfidence` and `QualityFlag` enums
- [`inversa/v1/grounding.proto`](inversa/v1/grounding.proto) — the UI-grounding contract: `EvidenceRefs`, `DownwindMatch`, `McpToolEnvelope`, `TimelineBucket`, `MapSnapshot`, `BoundingBox`
- `buf.yaml` / `buf.gen.yaml` — lint + offline codegen configuration

**Regenerate bindings with `make proto`** (buf lint → protolint → buf generate). Output lands in `packages/shared-schemas` (Python) and `apps/web/src/generated` (TypeScript). Never hand-write duplicate dataclasses or interfaces for these types — edit the `.proto` files here and regenerate.

Governing spec: [`specs/01-data-contracts.md`](../../specs/01-data-contracts.md)
