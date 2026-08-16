import asyncio

from services.api.vigia_api.config import get_settings
from services.api.vigia_api.database import VigiaDatabase

from .client import FirmsClient, FirmsError, FirmsSource
from .ingest import FirmsIngestConfig, ingest_source
from .repository import FirmsPersistenceError, FirmsRepository


async def run() -> int:
    settings = get_settings()
    if settings.SUPABASE_DB_URL is None:
        print("SIN_DATOS: falta SUPABASE_DB_URL.")
        return 2
    if settings.NASA_FIRMS_MAP_KEY is None:
        print("SIN_DATOS: falta NASA_FIRMS_MAP_KEY.")
        return 2

    database = VigiaDatabase(settings.SUPABASE_DB_URL.get_secret_value())
    client = FirmsClient(settings.NASA_FIRMS_MAP_KEY.get_secret_value())
    repository = FirmsRepository(database)
    exit_code = 0
    try:
        for source in FirmsSource:
            try:
                result = await ingest_source(
                    client,
                    repository,
                    source,
                    config=FirmsIngestConfig(code_commit=settings.VIGIA_CODE_COMMIT),
                )
            except FirmsError as exc:
                print(f"{source.value}: {exc.error_code} — {exc}")
                exit_code = 1
                continue
            except FirmsPersistenceError:
                print(f"{source.value}: FIRMS_PERSISTENCE_ERROR")
                exit_code = 1
                continue
            print(
                f"{source.value}: recibidos={result.records_received} "
                f"escritos={result.records_written}"
            )
    finally:
        await database.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
