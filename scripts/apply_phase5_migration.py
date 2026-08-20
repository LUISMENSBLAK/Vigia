from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg

from services.api.vigia_api.config import get_settings

MIGRATION_SQL = Path("database/migrations/20260820030000_phase5_national_risk.sql").read_text(
    encoding="utf-8"
)


async def main() -> None:
    settings = get_settings()
    if settings.SUPABASE_DB_URL is None:
        raise SystemExit("SUPABASE_DB_URL no configurada")
    try:
        connection = await asyncpg.connect(
            settings.SUPABASE_DB_URL.get_secret_value(),
            statement_cache_size=0,
            timeout=20,
            command_timeout=180,
        )
    except asyncpg.InvalidPasswordError:
        raise SystemExit("NO APLICADA: autenticación PostgreSQL rechazada") from None
    except (OSError, TimeoutError):
        raise SystemExit("NO APLICADA: red o DNS no disponible") from None
    try:
        exists = await connection.fetchval("select to_regclass('vigia.risk_runs') is not null")
        if exists:
            print("Phase 5 migration already present; no changes applied.")
            return
        try:
            async with connection.transaction():
                await connection.execute(MIGRATION_SQL)
        except asyncpg.PostgresError as exc:
            raise SystemExit(
                f"NO APLICADA: PostgreSQL rechazó Fase 5 (SQLSTATE {exc.sqlstate or 'DESCONOCIDO'})"
            ) from None
        print("Phase 5 migration applied.")
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(main())
