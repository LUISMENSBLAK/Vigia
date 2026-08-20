from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg

from services.api.vigia_api.config import get_settings

MIGRATION = Path("database/migrations/20260820040000_phase6_historical_replay.sql")
MIGRATION_SQL = MIGRATION.read_text(encoding="utf-8")
HARDENING = Path("database/migrations/20260820040100_phase6_replay_immutability.sql")
HARDENING_SQL = HARDENING.read_text(encoding="utf-8")


async def apply() -> None:
    settings = get_settings()
    if settings.SUPABASE_DB_URL is None:
        raise SystemExit("SUPABASE_DB_URL no configurada")
    connection = await asyncpg.connect(
        settings.SUPABASE_DB_URL.get_secret_value(), timeout=20, command_timeout=180
    )
    try:
        phase5 = await connection.fetchval(
            "select to_regclass('vigia.risk_runs') is not null"
        )
        installed = await connection.fetchval(
            "select to_regclass('vigia.replay_cases') is not null"
        )
        if not phase5:
            raise SystemExit("Fase 5 no está instalada; no se aplica Fase 6")
        if not installed:
            await connection.execute(MIGRATION_SQL)
            print("Migración Fase 6 aplicada.")
        hardening_installed = await connection.fetchval(
            """
            select exists (
              select 1 from pg_trigger
              where tgname = 'replay_cases_immutable_when_frozen' and not tgisinternal
            )
            """
        )
        if hardening_installed:
            print("Fase 6 ya estaba presente; no se aplicó una migración duplicada.")
            return
        await connection.execute(HARDENING_SQL)
        print("Hardening de inmutabilidad Fase 6 aplicado.")
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(apply())
