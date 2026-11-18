"""Grounding helpers that serialize tool results into McpToolEnvelope JSON (spec-04 §2)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from google.protobuf.json_format import MessageToDict
from inversa.v1 import telemetry_pb2
from inversa.v1.grounding_pb2 import BoundingBox, DownwindMatch, EvidenceRefs, McpToolEnvelope

QUALITY_FLAG_PROTO_NAMES: dict[str, telemetry_pb2.QualityFlag] = {
    "valid": telemetry_pb2.QUALITY_FLAG_VALID,
    "stale": telemetry_pb2.QUALITY_FLAG_STALE,
    "outlier": telemetry_pb2.QUALITY_FLAG_OUTLIER,
}


def build_envelope(
    *,
    summary_for_llm: str,
    data_quality_notes: Sequence[str],
    fire_ids: Sequence[str],
    station_ids: Sequence[str],
    focus_timestamp: datetime,
    bbox_focus: tuple[float, float, float, float] | None,
    matches: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Serialize one tool result into the spec-04 envelope JSON dictionary.

    ``bbox_focus`` is a flat ``(min_lon, min_lat, max_lon, max_lat)`` tuple; the
    proto renders a nested object, so it is flattened back to an array after
    JSON conversion.
    """
    envelope = McpToolEnvelope(
        summary_for_llm=summary_for_llm,
        data_quality_notes=list(data_quality_notes),
        evidence_refs=EvidenceRefs(
            fire_ids=list(fire_ids),
            station_ids=list(station_ids),
            focus_timestamp=focus_timestamp,
            bbox_focus=(
                BoundingBox(
                    min_lon=bbox_focus[0],
                    min_lat=bbox_focus[1],
                    max_lon=bbox_focus[2],
                    max_lat=bbox_focus[3],
                )
                if bbox_focus is not None
                else None
            ),
        ),
        matches=[_normalize_match(match) for match in matches],
    )
    return serialize_envelope(envelope)


def serialize_envelope(envelope: McpToolEnvelope) -> dict[str, Any]:
    """Convert an McpToolEnvelope proto message into the wire JSON dictionary."""
    payload: dict[str, Any] = MessageToDict(
        envelope,
        preserving_proto_field_name=True,
        always_print_fields_with_no_presence=True,
    )
    evidence = payload["evidence_refs"]
    nested_bbox = evidence.pop("bbox_focus", None)
    if isinstance(nested_bbox, Mapping) and "min_lon" in nested_bbox:
        evidence["bbox_focus"] = [
            nested_bbox["min_lon"],
            nested_bbox["min_lat"],
            nested_bbox["max_lon"],
            nested_bbox["max_lat"],
        ]
    return payload


def empty_envelope(
    *, summary_for_llm: str, notes: Sequence[str], focus_timestamp: datetime
) -> dict[str, Any]:
    """Build an envelope with no matches and no focus geometry."""
    return build_envelope(
        summary_for_llm=summary_for_llm,
        data_quality_notes=notes,
        fire_ids=[],
        station_ids=[],
        focus_timestamp=focus_timestamp,
        bbox_focus=None,
        matches=[],
    )


def _normalize_match(raw: Mapping[str, Any]) -> DownwindMatch:
    flag = str(raw.get("quality_flag", "") or "")
    return DownwindMatch(
        fire_id=str(raw.get("fire_id", "") or ""),
        fire_frp=_as_float(raw.get("fire_frp")),
        station_id=str(raw.get("station_id", "") or ""),
        station_name=str(raw.get("station_name", "") or ""),
        pm25=_as_float(raw.get("pm25")),
        quality_flag=QUALITY_FLAG_PROTO_NAMES.get(flag, telemetry_pb2.QUALITY_FLAG_UNSPECIFIED),
        distance_km=_as_float(raw.get("distance_km")),
        plume_bearing_deg=_as_float(raw.get("plume_bearing_deg")),
        wind_speed_10m=_as_float(raw.get("wind_speed_10m")),
        angle_diff_deg=_as_float(raw.get("angle_diff_deg")),
    )


def _as_float(value: Any) -> float:
    return float(value) if value is not None else 0.0
