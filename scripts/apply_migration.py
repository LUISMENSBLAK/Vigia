import asyncio
from pathlib import Path

import asyncpg
from anyio import Path as AsyncPath

from services.api.vigia_api.config import get_settings

MIGRATION = Path("database/migrations/20260816000000_initial_vigia.sql")


async def apply() -> int:
    settings = get_settings()
    if settings.SUPABASE_DB_URL is None:
        print("SIN_DATOS: falta SUPABASE_DB_URL.")
        return 2
    connection = await asyncpg.connect(settings.SUPABASE_DB_URL.get_secret_value())
    try:
        existing = await connection.fetchval("select to_regclass('vigia.sources') is not null")
        if existing:
            print("NO APLICADA: vigia.sources ya existe; se requiere auditoría manual de versión.")
            return 3
        sql = await AsyncPath(MIGRATION).read_text(encoding="utf-8")
        async with connection.transaction():
            await connection.execute(sql)
        print("APLICADA: migración inicial VIGÍA completada.")
        return 0
    finally:
        await connection.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(apply()))
