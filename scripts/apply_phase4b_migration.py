import asyncio
from pathlib import Path

import asyncpg
from anyio import Path as AsyncPath

from services.api.vigia_api.config import get_settings

MIGRATION = Path("database/migrations/20260820020000_phase4b_real_geospatial.sql")


async def apply() -> int:
    settings = get_settings()
    if settings.SUPABASE_DB_URL is None:
        print("SIN_DATOS: falta SUPABASE_DB_URL.")
        return 2
    try:
        connection = await asyncpg.connect(
            settings.SUPABASE_DB_URL.get_secret_value(), timeout=20, command_timeout=180
        )
    except asyncpg.InvalidPasswordError:
        print("NO APLICADA: autenticación PostgreSQL rechazada.")
        return 1
    except (OSError, TimeoutError):
        print("NO APLICADA: red o DNS no disponible.")
        return 1
    try:
        phase4 = await connection.fetchval(
            "select to_regclass('vigia.geospatial_products') is not null"
        )
        phase4b = await connection.fetchval(
            """
            select exists (
              select from information_schema.columns
              where table_schema = 'vigia' and table_name = 'source_health'
                and column_name = 'last_product_at'
            )
            """
        )
        if not phase4:
            print("NO APLICADA: falta la migración de Fase 4.")
            return 3
        if phase4b:
            print("NO APLICADA: Fase 4B ya existe; requiere auditoría de versión.")
            return 3
        sql = await AsyncPath(MIGRATION).read_text(encoding="utf-8")
        try:
            async with connection.transaction():
                await connection.execute(sql)
        except asyncpg.PostgresError as exc:
            sqlstate = exc.sqlstate or "DESCONOCIDO"
            print(f"NO APLICADA: PostgreSQL rechazó Fase 4B (SQLSTATE {sqlstate}).")
            return 1
        print("APLICADA: migración VIGÍA Fase 4B completada.")
        return 0
    finally:
        await connection.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(apply()))
