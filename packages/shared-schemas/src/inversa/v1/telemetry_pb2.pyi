import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class FireConfidence(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    FIRE_CONFIDENCE_UNSPECIFIED: _ClassVar[FireConfidence]
    FIRE_CONFIDENCE_LOW: _ClassVar[FireConfidence]
    FIRE_CONFIDENCE_NOMINAL: _ClassVar[FireConfidence]
    FIRE_CONFIDENCE_HIGH: _ClassVar[FireConfidence]

class QualityFlag(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    QUALITY_FLAG_UNSPECIFIED: _ClassVar[QualityFlag]
    QUALITY_FLAG_VALID: _ClassVar[QualityFlag]
    QUALITY_FLAG_OUTLIER: _ClassVar[QualityFlag]
    QUALITY_FLAG_STALE: _ClassVar[QualityFlag]
FIRE_CONFIDENCE_UNSPECIFIED: FireConfidence
FIRE_CONFIDENCE_LOW: FireConfidence
FIRE_CONFIDENCE_NOMINAL: FireConfidence
FIRE_CONFIDENCE_HIGH: FireConfidence
QUALITY_FLAG_UNSPECIFIED: QualityFlag
QUALITY_FLAG_VALID: QualityFlag
QUALITY_FLAG_OUTLIER: QualityFlag
QUALITY_FLAG_STALE: QualityFlag

class FireDetection(_message.Message):
    __slots__ = ("fire_id", "observed_at", "ingested_at", "lat", "lon", "frp", "confidence", "satellite")
    FIRE_ID_FIELD_NUMBER: _ClassVar[int]
    OBSERVED_AT_FIELD_NUMBER: _ClassVar[int]
    INGESTED_AT_FIELD_NUMBER: _ClassVar[int]
    LAT_FIELD_NUMBER: _ClassVar[int]
    LON_FIELD_NUMBER: _ClassVar[int]
    FRP_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    SATELLITE_FIELD_NUMBER: _ClassVar[int]
    fire_id: str
    observed_at: _timestamp_pb2.Timestamp
    ingested_at: _timestamp_pb2.Timestamp
    lat: float
    lon: float
    frp: float
    confidence: FireConfidence
    satellite: str
    def __init__(self, fire_id: _Optional[str] = ..., observed_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., ingested_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., lat: _Optional[float] = ..., lon: _Optional[float] = ..., frp: _Optional[float] = ..., confidence: _Optional[_Union[FireConfidence, str]] = ..., satellite: _Optional[str] = ...) -> None: ...

class AirQualityReading(_message.Message):
    __slots__ = ("measurement_id", "station_id", "station_name", "observed_at", "ingested_at", "lat", "lon", "pm25", "quality_flag")
    MEASUREMENT_ID_FIELD_NUMBER: _ClassVar[int]
    STATION_ID_FIELD_NUMBER: _ClassVar[int]
    STATION_NAME_FIELD_NUMBER: _ClassVar[int]
    OBSERVED_AT_FIELD_NUMBER: _ClassVar[int]
    INGESTED_AT_FIELD_NUMBER: _ClassVar[int]
    LAT_FIELD_NUMBER: _ClassVar[int]
    LON_FIELD_NUMBER: _ClassVar[int]
    PM25_FIELD_NUMBER: _ClassVar[int]
    QUALITY_FLAG_FIELD_NUMBER: _ClassVar[int]
    measurement_id: str
    station_id: str
    station_name: str
    observed_at: _timestamp_pb2.Timestamp
    ingested_at: _timestamp_pb2.Timestamp
    lat: float
    lon: float
    pm25: float
    quality_flag: QualityFlag
    def __init__(self, measurement_id: _Optional[str] = ..., station_id: _Optional[str] = ..., station_name: _Optional[str] = ..., observed_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., ingested_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., lat: _Optional[float] = ..., lon: _Optional[float] = ..., pm25: _Optional[float] = ..., quality_flag: _Optional[_Union[QualityFlag, str]] = ...) -> None: ...

class WindVector(_message.Message):
    __slots__ = ("grid_id", "observed_at", "ingested_at", "lat", "lon", "wind_speed_10m", "wind_direction_10m", "boundary_layer_height")
    GRID_ID_FIELD_NUMBER: _ClassVar[int]
    OBSERVED_AT_FIELD_NUMBER: _ClassVar[int]
    INGESTED_AT_FIELD_NUMBER: _ClassVar[int]
    LAT_FIELD_NUMBER: _ClassVar[int]
    LON_FIELD_NUMBER: _ClassVar[int]
    WIND_SPEED_10M_FIELD_NUMBER: _ClassVar[int]
    WIND_DIRECTION_10M_FIELD_NUMBER: _ClassVar[int]
    BOUNDARY_LAYER_HEIGHT_FIELD_NUMBER: _ClassVar[int]
    grid_id: str
    observed_at: _timestamp_pb2.Timestamp
    ingested_at: _timestamp_pb2.Timestamp
    lat: float
    lon: float
    wind_speed_10m: float
    wind_direction_10m: float
    boundary_layer_height: float
    def __init__(self, grid_id: _Optional[str] = ..., observed_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., ingested_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., lat: _Optional[float] = ..., lon: _Optional[float] = ..., wind_speed_10m: _Optional[float] = ..., wind_direction_10m: _Optional[float] = ..., boundary_layer_height: _Optional[float] = ...) -> None: ...
