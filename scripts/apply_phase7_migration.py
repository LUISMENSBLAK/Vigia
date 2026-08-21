from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg

from services.api.vigia_api.config import get_settings

MIGRATION = Path("database/migrations/20260821000000_phase7_scientific_validation.sql")
MIGRATION_SQL = MIGRATION.read_text(encoding="utf-8")


async def apply() -> None:
    settings = get_settings()
    if settings.SUPABASE_DB_URL is None:
        raise SystemExit("SUPABASE_DB_URL no configurada")
    connection = await asyncpg.connect(
        settings.SUPABASE_DB_URL.get_secret_value(), timeout=20, command_timeout=300
    )
    try:
        phase6 = await connection.fetchval("select to_regclass('vigia.replay_cases') is not null")
        installed = await connection.fetchval(
            "select to_regclass('vigia.validation_dataset_versions') is not null"
        )
        if not phase6:
            raise SystemExit("Fase 6 no está instalada; no se aplica Fase 7")
        if installed:
            print("Fase 7 ya estaba presente; no se aplicó una migración duplicada.")
            return
        await connection.execute(MIGRATION_SQL)
        print("Migración Fase 7 aplicada.")
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(apply())
