from datetime import datetime
from enum import StrEnum
from typing import Any
from urllib.parse import parse_qsl, urlsplit
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

FORBIDDEN_URI_PARAMETERS = frozenset(
    {"token", "access_token", "apikey", "api_key", "key", "signature", "sig"}
)


def safe_source_uri(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("source_uri no puede contener credenciales ni firmas.")
    parameter_names = {name.casefold() for name, _ in parse_qsl(parsed.query)}
    if parameter_names & FORBIDDEN_URI_PARAMETERS:
        raise ValueError("source_uri no puede contener credenciales ni firmas.")
    return value


class AvailabilityState(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    PROCESSING = "PROCESSING"
    ERROR = "ERROR"


class GeospatialLayer(StrEnum):
    ELEVATION = "ELEVATION"
    SLOPE = "SLOPE"
    ASPECT = "ASPECT"
    TERRAIN_RUGGEDNESS = "TERRAIN_RUGGEDNESS"
    NDVI = "NDVI"
    NDMI = "NDMI"
    NBR = "NBR"
    LAND_COVER = "LAND_COVER"
    LIDAR_DTM = "LIDAR_DTM"
    LIDAR_DSM = "LIDAR_DSM"
    CANOPY_HEIGHT = "CANOPY_HEIGHT"
    FUEL_PROXY = "FUEL_PROXY"


class GeospatialProduct(BaseModel):
    id: UUID | None = None
    provider: str
    dataset: str
    product_id: str
    layer: GeospatialLayer
    availability: AvailabilityState
    observed_at: datetime | None = None
    processed_at: datetime | None = None
    source_uri: str | None = None
    storage_uri: str | None = None
    footprint_geojson: dict[str, Any]
    source_crs: str
    output_crs: str
    source_resolution_m: float = Field(gt=0)
    output_resolution_m: float = Field(gt=0)
    resampling_algorithm: str | None = None
    nodata: float | int | None = None
    quality: dict[str, Any] = Field(default_factory=dict)
    input_hashes: tuple[str, ...] = ()
    output_hash: str | None = None
    configuration_hash: str
    software_version: str
    algorithm: str
    is_experimental: bool = False

    @field_validator("source_uri")
    @classmethod
    def source_uri_has_no_credentials(cls, value: str | None) -> str | None:
        return safe_source_uri(value) if value is not None else None


class ContextValue(BaseModel):
    layer: GeospatialLayer
    value: float | int | str | None = None
    units: str | None = None
    availability: AvailabilityState
    observed_at: datetime | None = None
    processed_at: datetime | None = None
    resolution_m: float | None = None
    source: str | None = None
    product_id: str | None = None
    quality: dict[str, Any] = Field(default_factory=dict)
    provenance_id: str | None = None
    message: str | None = None


class DownloadManifest(BaseModel):
    provider: str
    product_id: str
    source_uri: str
    requested_at: datetime
    downloaded_at: datetime | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    checksum_sha256: str | None = None
    etag: str | None = None
    status: AvailabilityState
    aoi_hash: str
    request_id: str = Field(min_length=1, max_length=160)
    error_code: str | None = None

    @field_validator("source_uri")
    @classmethod
    def source_uri_has_no_credentials(cls, value: str) -> str:
        return safe_source_uri(value)
