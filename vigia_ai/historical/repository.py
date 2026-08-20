from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text

from services.api.vigia_api.database import VigiaDatabase

from .models import HistoricalFireEvent, TimestampPrecision


@dataclass(frozen=True, slots=True)
class CorpusPersistResult:
    events: int
    references: int
    timestamps: int


class HistoricalCorpusRepository:
    source_code = "JCYL_HISTORICAL_FIRES"

    def __init__(self, database: VigiaDatabase) -> None:
        self._database = database

    async def persist(self, events: tuple[HistoricalFireEvent, ...]) -> CorpusPersistResult:
        event_count = reference_count = timestamp_count = 0
        async with self._database.transaction() as connection:
            source_id = await connection.scalar(
                text("select id from vigia.sources where code = :code"),
                {"code": self.source_code},
            )
            if source_id is None:
                raise RuntimeError("La fuente histórica oficial no está en el catálogo")
            for event in events:
                start = event.official_start
                event_row = (
                    (
                        await connection.execute(
                            text(
                                """
                                insert into vigia.historical_fires (
                                  external_id, name, started_at, origin, source_id, quality,
                                  event_key, vigia_code, region, provinces, municipality,
                                  reference_quality, canonical_metadata, updated_at
                                ) values (
                                  :external_id, :name, :started_at,
                                  case when cast(:longitude as double precision) is null
                                    then null else
                                    extensions.st_setsrid(
                                      extensions.st_makepoint(
                                        cast(:longitude as double precision),
                                        cast(:latitude as double precision)
                                      ), 4326
                                    )::extensions.geography end,
                                  :source_id, cast(:quality as jsonb), :event_key, :vigia_code,
                                  :region, :provinces, :municipality,
                                  cast(:reference_quality as vigia.reference_quality),
                                  cast(:metadata as jsonb), now()
                                ) on conflict (event_key) do update set
                                  name = excluded.name,
                                  started_at = coalesce(
                                    vigia.historical_fires.started_at, excluded.started_at
                                  ),
                                  origin = coalesce(vigia.historical_fires.origin, excluded.origin),
                                  reference_quality = excluded.reference_quality,
                                  canonical_metadata = excluded.canonical_metadata,
                                  updated_at = now()
                                returning id
                                """
                            ),
                            {
                                "external_id": event.event_key,
                                "name": event.name,
                                "started_at": start.instant if start else None,
                                "longitude": event.longitude,
                                "latitude": event.latitude,
                                "source_id": source_id,
                                "quality": json.dumps(
                                    {"reference_quality": event.reference_quality.value}
                                ),
                                "event_key": event.event_key,
                                "vigia_code": event.vigia_code,
                                "region": event.region,
                                "provinces": list(event.province),
                                "municipality": event.municipality,
                                "reference_quality": event.reference_quality.value,
                                "metadata": json.dumps(
                                    {
                                        "canonical_hash": event.canonical_hash(),
                                        "reference_count": len(event.references),
                                        "maximum_reported_area_ha": event.maximum_reported_area_ha,
                                    }
                                ),
                            },
                        )
                    )
                    .mappings()
                    .one()
                )
                event_count += 1
                for reference in event.references:
                    existing = await connection.scalar(
                        text(
                            """
                            select id from vigia.historical_fire_references
                            where source_id = :source_id
                              and external_record_id = :record_id
                              and raw_checksum_sha256 = :checksum
                            """
                        ),
                        {
                            "source_id": source_id,
                            "record_id": reference.record_id,
                            "checksum": reference.checksum_sha256,
                        },
                    )
                    if existing is not None:
                        continue
                    reference_id = await connection.scalar(
                        text(
                            """
                            insert into vigia.historical_fire_references (
                              historical_fire_id, source_id, external_record_id, source_uri,
                              license_uri, retrieved_at, raw_checksum_sha256, original_record,
                              normalized_metadata, reference_quality
                            ) values (
                              :historical_fire_id, :source_id, :record_id, :source_uri,
                              :license_uri, :retrieved_at, :checksum, cast(:original as jsonb),
                              cast(:metadata as jsonb),
                              cast(:reference_quality as vigia.reference_quality)
                            ) returning id
                            """
                        ),
                        {
                            "historical_fire_id": event_row["id"],
                            "source_id": source_id,
                            "record_id": reference.record_id,
                            "source_uri": reference.source_uri,
                            "license_uri": reference.license_uri,
                            "retrieved_at": reference.retrieved_at,
                            "checksum": reference.checksum_sha256,
                            "original": json.dumps(reference.original, ensure_ascii=True),
                            "metadata": json.dumps(
                                {
                                    "province": reference.province,
                                    "municipality": reference.municipality,
                                    "region": reference.region,
                                    "area_ha": reference.area_ha,
                                    "cause": reference.cause,
                                    "official_status": reference.official_status,
                                }
                            ),
                            "reference_quality": reference.quality.value,
                        },
                    )
                    if not isinstance(reference_id, UUID):
                        raise RuntimeError("No se pudo persistir la referencia histórica")
                    reference_count += 1
                    for stamp in reference.timestamps:
                        await connection.execute(
                            text(
                                """
                                insert into vigia.historical_fire_timestamps (
                                  reference_id, meaning, instant, calendar_date, precision,
                                  timezone_name, quality
                                ) values (
                                  :reference_id, :meaning, :instant, :calendar_date,
                                  cast(:precision as vigia.timestamp_precision),
                                  :timezone_name, cast(:quality as jsonb)
                                )
                                """
                            ),
                            {
                                "reference_id": reference_id,
                                "meaning": stamp.meaning,
                                "instant": stamp.instant,
                                "calendar_date": stamp.calendar_date,
                                "precision": stamp.precision.value,
                                "timezone_name": stamp.timezone,
                                "quality": json.dumps(stamp.quality),
                            },
                        )
                        timestamp_count += 1
        return CorpusPersistResult(event_count, reference_count, timestamp_count)


def timestamp_parameters(stamp: Any) -> dict[str, Any]:
    """Small public helper for migration/contract tests."""
    precision = TimestampPrecision(stamp.precision)
    return {
        "instant": stamp.instant if precision is not TimestampPrecision.DATE_ONLY else None,
        "calendar_date": stamp.calendar_date
        if precision is TimestampPrecision.DATE_ONLY
        else None,
        "precision": precision.value,
    }
