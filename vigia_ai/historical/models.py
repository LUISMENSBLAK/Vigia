from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class TimestampPrecision(StrEnum):
    DATE_ONLY = "DATE_ONLY"
    HOUR = "HOUR"
    MINUTE = "MINUTE"
    EXACT = "EXACT"
    UNKNOWN = "UNKNOWN"


class ReferenceQuality(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class HistoricalTimestamp(BaseModel):
    meaning: str
    instant: datetime | None = None
    calendar_date: date | None = None
    precision: TimestampPrecision
    source: str
    timezone: str | None = None
    quality: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def representation_matches_precision(self) -> HistoricalTimestamp:
        if self.precision is TimestampPrecision.DATE_ONLY:
            if self.calendar_date is None or self.instant is not None:
                raise ValueError("DATE_ONLY conserva fecha sin inventar una hora")
        elif self.precision is TimestampPrecision.UNKNOWN:
            if self.instant is not None or self.calendar_date is not None:
                raise ValueError("UNKNOWN no debe contener un timestamp inventado")
        elif self.instant is None or self.instant.tzinfo is None:
            raise ValueError("Los timestamps temporales requieren zona horaria")
        return self


class HistoricalFireReference(BaseModel):
    reference_id: str
    provider: str
    dataset: str
    record_id: str
    source_uri: str
    retrieved_at: datetime
    checksum_sha256: str
    license_uri: str | None = None
    province: tuple[str, ...] = ()
    municipality: str | None = None
    region: str | None = None
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    area_ha: float | None = Field(default=None, ge=0)
    cause: str | None = None
    official_status: str | None = None
    quality: ReferenceQuality = ReferenceQuality.UNKNOWN
    timestamps: tuple[HistoricalTimestamp, ...] = ()
    original: dict[str, Any]

    @model_validator(mode="after")
    def coordinates_are_paired(self) -> HistoricalFireReference:
        if (self.longitude is None) != (self.latitude is None):
            raise ValueError("Las coordenadas históricas deben aparecer juntas")
        if self.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at requiere zona horaria")
        return self


class HistoricalFireEvent(BaseModel):
    event_id: str
    event_key: str
    vigia_code: str
    name: str | None = None
    province: tuple[str, ...] = ()
    municipality: str | None = None
    region: str | None = None
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    reference_quality: ReferenceQuality
    references: tuple[HistoricalFireReference, ...]

    def canonical_hash(self) -> str:
        payload = self.model_dump(mode="json")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    @property
    def official_start(self) -> HistoricalTimestamp | None:
        starts = [
            stamp
            for reference in self.references
            for stamp in reference.timestamps
            if stamp.meaning == "official_start_time"
        ]
        return min(
            starts,
            key=lambda item: item.instant
            or datetime.max.replace(tzinfo=self.references[0].retrieved_at.tzinfo),
            default=None,
        )

    @property
    def maximum_reported_area_ha(self) -> float | None:
        values = [item.area_ha for item in self.references if item.area_ha is not None]
        return max(values) if values else None
