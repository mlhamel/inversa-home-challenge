import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from inversa.v1 import telemetry_pb2 as _telemetry_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class BoundingBox(_message.Message):
    __slots__ = ("min_lon", "min_lat", "max_lon", "max_lat")
    MIN_LON_FIELD_NUMBER: _ClassVar[int]
    MIN_LAT_FIELD_NUMBER: _ClassVar[int]
    MAX_LON_FIELD_NUMBER: _ClassVar[int]
    MAX_LAT_FIELD_NUMBER: _ClassVar[int]
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float
    def __init__(self, min_lon: _Optional[float] = ..., min_lat: _Optional[float] = ..., max_lon: _Optional[float] = ..., max_lat: _Optional[float] = ...) -> None: ...

class EvidenceRefs(_message.Message):
    __slots__ = ("fire_ids", "station_ids", "focus_timestamp", "bbox_focus")
    FIRE_IDS_FIELD_NUMBER: _ClassVar[int]
    STATION_IDS_FIELD_NUMBER: _ClassVar[int]
    FOCUS_TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    BBOX_FOCUS_FIELD_NUMBER: _ClassVar[int]
    fire_ids: _containers.RepeatedScalarFieldContainer[str]
    station_ids: _containers.RepeatedScalarFieldContainer[str]
    focus_timestamp: _timestamp_pb2.Timestamp
    bbox_focus: BoundingBox
    def __init__(self, fire_ids: _Optional[_Iterable[str]] = ..., station_ids: _Optional[_Iterable[str]] = ..., focus_timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., bbox_focus: _Optional[_Union[BoundingBox, _Mapping]] = ...) -> None: ...

class DownwindMatch(_message.Message):
    __slots__ = ("fire_id", "fire_frp", "station_id", "station_name", "pm25", "quality_flag", "distance_km", "plume_bearing_deg", "wind_speed_10m", "angle_diff_deg")
    FIRE_ID_FIELD_NUMBER: _ClassVar[int]
    FIRE_FRP_FIELD_NUMBER: _ClassVar[int]
    STATION_ID_FIELD_NUMBER: _ClassVar[int]
    STATION_NAME_FIELD_NUMBER: _ClassVar[int]
    PM25_FIELD_NUMBER: _ClassVar[int]
    QUALITY_FLAG_FIELD_NUMBER: _ClassVar[int]
    DISTANCE_KM_FIELD_NUMBER: _ClassVar[int]
    PLUME_BEARING_DEG_FIELD_NUMBER: _ClassVar[int]
    WIND_SPEED_10M_FIELD_NUMBER: _ClassVar[int]
    ANGLE_DIFF_DEG_FIELD_NUMBER: _ClassVar[int]
    fire_id: str
    fire_frp: float
    station_id: str
    station_name: str
    pm25: float
    quality_flag: _telemetry_pb2.QualityFlag
    distance_km: float
    plume_bearing_deg: float
    wind_speed_10m: float
    angle_diff_deg: float
    def __init__(self, fire_id: _Optional[str] = ..., fire_frp: _Optional[float] = ..., station_id: _Optional[str] = ..., station_name: _Optional[str] = ..., pm25: _Optional[float] = ..., quality_flag: _Optional[_Union[_telemetry_pb2.QualityFlag, str]] = ..., distance_km: _Optional[float] = ..., plume_bearing_deg: _Optional[float] = ..., wind_speed_10m: _Optional[float] = ..., angle_diff_deg: _Optional[float] = ...) -> None: ...

class McpToolEnvelope(_message.Message):
    __slots__ = ("summary_for_llm", "data_quality_notes", "evidence_refs", "matches")
    SUMMARY_FOR_LLM_FIELD_NUMBER: _ClassVar[int]
    DATA_QUALITY_NOTES_FIELD_NUMBER: _ClassVar[int]
    EVIDENCE_REFS_FIELD_NUMBER: _ClassVar[int]
    MATCHES_FIELD_NUMBER: _ClassVar[int]
    summary_for_llm: str
    data_quality_notes: _containers.RepeatedScalarFieldContainer[str]
    evidence_refs: EvidenceRefs
    matches: _containers.RepeatedCompositeFieldContainer[DownwindMatch]
    def __init__(self, summary_for_llm: _Optional[str] = ..., data_quality_notes: _Optional[_Iterable[str]] = ..., evidence_refs: _Optional[_Union[EvidenceRefs, _Mapping]] = ..., matches: _Optional[_Iterable[_Union[DownwindMatch, _Mapping]]] = ...) -> None: ...

class TimelineBucket(_message.Message):
    __slots__ = ("hour_bucket", "active_fires_count", "avg_pm25", "max_pm25", "active_stations", "stale_stations")
    HOUR_BUCKET_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_FIRES_COUNT_FIELD_NUMBER: _ClassVar[int]
    AVG_PM25_FIELD_NUMBER: _ClassVar[int]
    MAX_PM25_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_STATIONS_FIELD_NUMBER: _ClassVar[int]
    STALE_STATIONS_FIELD_NUMBER: _ClassVar[int]
    hour_bucket: _timestamp_pb2.Timestamp
    active_fires_count: int
    avg_pm25: float
    max_pm25: float
    active_stations: int
    stale_stations: int
    def __init__(self, hour_bucket: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., active_fires_count: _Optional[int] = ..., avg_pm25: _Optional[float] = ..., max_pm25: _Optional[float] = ..., active_stations: _Optional[int] = ..., stale_stations: _Optional[int] = ...) -> None: ...

class MapSnapshot(_message.Message):
    __slots__ = ("timestamp", "fires", "stations", "wind_vectors")
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    FIRES_FIELD_NUMBER: _ClassVar[int]
    STATIONS_FIELD_NUMBER: _ClassVar[int]
    WIND_VECTORS_FIELD_NUMBER: _ClassVar[int]
    timestamp: _timestamp_pb2.Timestamp
    fires: _containers.RepeatedCompositeFieldContainer[_telemetry_pb2.FireDetection]
    stations: _containers.RepeatedCompositeFieldContainer[_telemetry_pb2.AirQualityReading]
    wind_vectors: _containers.RepeatedCompositeFieldContainer[_telemetry_pb2.WindVector]
    def __init__(self, timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., fires: _Optional[_Iterable[_Union[_telemetry_pb2.FireDetection, _Mapping]]] = ..., stations: _Optional[_Iterable[_Union[_telemetry_pb2.AirQualityReading, _Mapping]]] = ..., wind_vectors: _Optional[_Iterable[_Union[_telemetry_pb2.WindVector, _Mapping]]] = ...) -> None: ...
