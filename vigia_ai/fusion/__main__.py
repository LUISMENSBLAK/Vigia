import argparse
import asyncio
from datetime import datetime

from services.api.vigia_api.config import get_settings
from services.api.vigia_api.database import VigiaDatabase
from services.api.vigia_api.logging import configure_logging

from .config import load_fusion_config
from .repository import FusionRepository
from .service import FusionService


def _timestamp(value: str) -> datetime:
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise argparse.ArgumentTypeError("Los timestamps deben incluir zona horaria.")
    return timestamp


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="VIGÍA Fusion Engine research baseline")
    command.add_argument("--from", dest="observed_from", required=True, type=_timestamp)
    command.add_argument("--to", dest="observed_to", required=True, type=_timestamp)
    command.add_argument("--as-of", required=True, type=_timestamp)
    return command


async def run() -> int:
    arguments = parser().parse_args()
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    if settings.SUPABASE_DB_URL is None:
        print("SIN_DATOS: falta SUPABASE_DB_URL; no se ejecutó Fusion Engine.")
        return 2
    config = load_fusion_config()
    database = VigiaDatabase(settings.SUPABASE_DB_URL.get_secret_value())
    try:
        execution = await FusionService(FusionRepository(database)).execute(
            config=config,
            observed_from=arguments.observed_from,
            observed_to=arguments.observed_to,
            as_of=arguments.as_of,
            software_version="vigia/0.3.0",
            code_commit=settings.VIGIA_CODE_COMMIT,
        )
    finally:
        await database.close()
    print(
        "FUSION COMPLETADA: "
        f"observaciones={execution.summary.eligible_observation_count} "
        f"clusters={execution.summary.candidate_count} "
        f"candidatos={execution.summary.incident_candidate_count} "
        f"incidentes_creados={execution.persistence.incidents_created} "
        f"incidentes_actualizados={execution.persistence.incidents_updated}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
