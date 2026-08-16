from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from .client import FirmsClient, FirmsError, FirmsQuotaError, FirmsSource
from .repository import FirmsPersistenceError, FirmsRepository, IngestResult, configuration_hash


@dataclass(frozen=True, slots=True)
class FirmsIngestConfig:
    bbox: tuple[float, float, float, float] = (-9.5, 35.7, 4.6, 43.9)
    day_range: int = 1
    software_version: str = "vigia/0.2.0"
    code_commit: str = "unavailable"


async def ingest_source(
    client: FirmsClient,
    repository: FirmsRepository,
    source: FirmsSource,
    *,
    config: FirmsIngestConfig | None = None,
) -> IngestResult:
    active_config = config or FirmsIngestConfig()
    started_at = datetime.now(UTC)
    run = await repository.begin_run(
        source_code=source.catalogue_code,
        software_version=active_config.software_version,
        configuration_hash_value=configuration_hash(
            source=source.value,
            bbox=active_config.bbox,
            day_range=active_config.day_range,
        ),
        request_id=str(uuid4()),
        started_at=started_at,
    )
    try:
        observations = await client.fetch_area(
            source,
            bbox=active_config.bbox,
            day_range=active_config.day_range,
        )
        return await repository.persist(
            run,
            observations,
            code_commit=active_config.code_commit,
            finished_at=datetime.now(UTC),
        )
    except FirmsError as exc:
        await repository.fail(
            run,
            error_code=exc.error_code,
            detail=str(exc),
            degraded=isinstance(exc, FirmsQuotaError),
        )
        raise
    except Exception as exc:
        with suppress(Exception):
            await repository.fail(
                run,
                error_code="FIRMS_PERSISTENCE_ERROR",
                detail="No se pudo completar la persistencia FIRMS.",
                degraded=False,
            )
        raise FirmsPersistenceError("No se pudo completar la persistencia FIRMS.") from exc
