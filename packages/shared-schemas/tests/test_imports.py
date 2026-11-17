from inversa.v1.grounding_pb2 import BoundingBox, EvidenceRefs, McpToolEnvelope
from inversa.v1.telemetry_pb2 import (
    AirQualityReading,
    FireConfidence,
    FireDetection,
    QualityFlag,
    WindVector,
)


def test_fire_detection_contract() -> None:
    fire = FireDetection(
        fire_id="a" * 16,
        confidence=FireConfidence.FIRE_CONFIDENCE_HIGH,
        satellite="VIIRS",
    )
    assert not fire.HasField("frp")
    fire.frp = 12.5
    assert fire.HasField("frp") and fire.frp == 12.5
    assert fire.confidence == FireConfidence.FIRE_CONFIDENCE_HIGH


def test_air_quality_reading_contract() -> None:
    reading = AirQualityReading(
        measurement_id="st-001_2026-01-01T00:00:00Z",
        station_id="st-001",
        station_name="Downtown",
        quality_flag=QualityFlag.QUALITY_FLAG_STALE,
    )
    assert not reading.HasField("pm25")
    assert reading.quality_flag == QualityFlag.QUALITY_FLAG_STALE


def test_wind_vector_contract() -> None:
    vector = WindVector(
        grid_id="g-001",
        wind_speed_10m=12.5,
        wind_direction_10m=270.0,
        boundary_layer_height=850.0,
    )
    assert vector.wind_speed_10m == 12.5


def test_mcp_envelope_contract() -> None:
    envelope = McpToolEnvelope(
        summary_for_llm="two stations flagged",
        data_quality_notes=["2 stations stale >2h"],
        evidence_refs=EvidenceRefs(
            fire_ids=["a" * 16],
            station_ids=["st-001"],
            bbox_focus=BoundingBox(
                min_lon=-80.0, min_lat=40.0, max_lon=-79.0, max_lat=41.0
            ),
        ),
    )
    assert envelope.evidence_refs.fire_ids == ["a" * 16]
    assert envelope.evidence_refs.bbox_focus is not None
    assert envelope.matches == []
