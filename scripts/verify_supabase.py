from __future__ import annotations

import asyncio
from dataclasses import dataclass

import asyncpg

from services.api.vigia_api.config import get_settings


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    passed: bool
    detail: str


async def role_can_select(connection: asyncpg.Connection[asyncpg.Record], role: str) -> bool:
    async with connection.transaction():
        await connection.execute(f"set local role {role}")
        await connection.fetchval("select count(*) from api.source_health")
    return True


async def role_cannot_read_internal_observations(
    connection: asyncpg.Connection[asyncpg.Record], role: str
) -> bool:
    try:
        async with connection.transaction():
            await connection.execute(f"set local role {role}")
            await connection.fetchval("select count(*) from vigia.fire_observations")
    except asyncpg.InsufficientPrivilegeError:
        return True
    return False


async def verify() -> int:
    settings = get_settings()
    if settings.SUPABASE_DB_URL is None:
        print("SIN_DATOS: falta SUPABASE_DB_URL.")
        return 2
    try:
        connection = await asyncpg.connect(
            settings.SUPABASE_DB_URL.get_secret_value(), timeout=20, command_timeout=30
        )
    except asyncpg.InvalidPasswordError:
        print("ERROR: SUPABASE_DB_URL — autenticación rechazada.")
        return 1
    except (OSError, TimeoutError):
        print("ERROR: SUPABASE_DB_URL — red o DNS no disponible.")
        return 1
    checks: list[Check] = []
    try:
        postgis = await connection.fetchval("select postgis_version()")
        checks.append(Check("PostGIS", isinstance(postgis, str), str(postgis)))
        distance = await connection.fetchval(
            """
            select extensions.st_distance(
              extensions.st_setsrid(
                extensions.st_makepoint(-4.7, 40.65), 4326
              )::extensions.geography,
              extensions.st_setsrid(
                extensions.st_makepoint(-4.7, 40.65), 4326
              )::extensions.geography
            )
            """
        )
        checks.append(Check("Query geoespacial", distance == 0, "distancia idéntica = 0 m"))
        rls_missing = await connection.fetchval(
            """
            select count(*)
            from pg_tables
            where schemaname = 'vigia' and not (rowsecurity and forcerowsecurity)
            """
        )
        checks.append(Check("RLS forzado", rls_missing == 0, f"tablas sin RLS: {rls_missing}"))
        for role in ("anon", "authenticated"):
            public_read = await role_can_select(connection, role)
            private_denied = await role_cannot_read_internal_observations(connection, role)
            checks.append(Check(f"{role}: vista pública", public_read, "api.source_health"))
            checks.append(
                Check(f"{role}: datos internos", private_denied, "lectura privilegiada denegada")
            )
        backend_read = await connection.fetchval(
            "select count(*) >= 0 from vigia.fire_observations"
        )
        checks.append(
            Check("backend privilegiado", bool(backend_read), "lectura interna permitida")
        )
    finally:
        await connection.close()

    for check in checks:
        print(f"{'GREEN' if check.passed else 'ERROR'}: {check.name} — {check.detail}")
    return 0 if all(check.passed for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(verify()))
