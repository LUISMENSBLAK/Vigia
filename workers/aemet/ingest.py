import hashlib
from contextlib import suppress
from datetime import UTC, datetime
from uuid import uuid4

from .client import AemetClient, AemetError
from .repository import AemetRepository


async def ingest_aemet(
    client: AemetClient,
    repository: AemetRepository,
    *,
    code_commit: str = "unavailable",
) -> int:
    run = await repository.begin_run(
        started_at=datetime.now(UTC),
        request_id=str(uuid4()),
        software_version="vigia/0.2.0",
        configuration_hash=hashlib.sha256(b"aemet:conventional-observations:all:v1").hexdigest(),
    )
    try:
        observations = await client.fetch_observations()
        return await repository.persist(
            run, observations, code_commit=code_commit, finished_at=datetime.now(UTC)
        )
    except AemetError as exc:
        await repository.fail(
            run,
            error_code=exc.error_code,
            detail=str(exc),
            finished_at=datetime.now(UTC),
        )
        raise
    except Exception:
        with suppress(Exception):
            await repository.fail(
                run,
                error_code="AEMET_PERSISTENCE_ERROR",
                detail="No se pudo completar la persistencia AEMET.",
                finished_at=datetime.now(UTC),
            )
        raise
