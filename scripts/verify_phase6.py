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


async def verify() -> int:
    settings = get_settings()
    if settings.SUPABASE_DB_URL is None:
        print("NO VERIFICADO: falta SUPABASE_DB_URL.")
        return 2
    connection = await asyncpg.connect(
        settings.SUPABASE_DB_URL.get_secret_value(), timeout=20, command_timeout=60
    )
    checks: list[Check] = []
    try:
        tables = await connection.fetchval(
            """
            select count(*) from information_schema.tables where table_schema = 'vigia'
              and table_name in (
                'historical_fire_references', 'historical_fire_timestamps',
                'historical_fire_perimeters', 'replay_cases', 'replay_inputs',
                'replay_runs', 'replay_steps'
              )
            """
        )
        checks.append(Check("tablas Fase 6", tables == 7, f"{tables}/7"))
        indexes = await connection.fetchval(
            """
            select count(*) from pg_indexes where schemaname = 'vigia'
              and indexname in (
                'historical_fire_references_event_idx', 'historical_fire_timestamps_time_idx',
                'historical_fire_perimeters_geometry_gist', 'replay_cases_aoi_gist',
                'replay_cases_time_idx', 'replay_inputs_case_time_idx',
                'replay_inputs_location_gist', 'replay_runs_case_started_idx',
                'replay_runs_state_idx', 'replay_steps_run_time_idx'
              )
            """
        )
        checks.append(Check("índices Fase 6", indexes == 10, f"{indexes}/10"))
        rls = await connection.fetchval(
            """
            select count(*) from pg_class relation
            join pg_namespace namespace on namespace.oid = relation.relnamespace
            where namespace.nspname = 'vigia'
              and relation.relname in (
                'historical_fire_references', 'historical_fire_timestamps',
                'historical_fire_perimeters', 'replay_cases', 'replay_inputs',
                'replay_runs', 'replay_steps'
              ) and relation.relrowsecurity and relation.relforcerowsecurity
            """
        )
        checks.append(Check("RLS forzado", rls == 7, f"{rls}/7"))
        grants = await connection.fetchval(
            """
            select count(*) from information_schema.role_table_grants
            where table_schema = 'vigia'
              and table_name in ('replay_cases', 'replay_inputs', 'replay_runs', 'replay_steps')
              and grantee in ('anon', 'authenticated')
              and privilege_type in ('INSERT', 'UPDATE', 'DELETE')
            """
        )
        checks.append(Check("sin escritura cliente", grants == 0, f"{grants} grants"))
        isolation = await connection.fetchval(
            """
            select count(*) from pg_constraint constraint_row
            join pg_class relation on relation.oid = constraint_row.conrelid
            join pg_namespace namespace on namespace.oid = relation.relnamespace
            where namespace.nspname = 'vigia' and relation.relname = 'replay_runs'
              and pg_get_constraintdef(constraint_row.oid) like '%live_state_mutated = false%'
            """
        )
        checks.append(Check("aislamiento LIVE", isolation == 1, f"{isolation}/1"))
        immutable = await connection.fetchval(
            """
            select count(*) from pg_trigger
            where tgname = 'replay_cases_immutable_when_frozen' and not tgisinternal
            """
        )
        checks.append(Check("manifest congelado", immutable == 1, f"{immutable}/1"))
        mutable_cases = await connection.fetchval(
            "select count(*) from vigia.replay_cases where not frozen"
        )
        checks.append(Check("casos no mutables", mutable_cases == 0, f"{mutable_cases} abiertos"))
    finally:
        await connection.close()
    for check in checks:
        print(f"{'GREEN' if check.passed else 'ERROR'}: {check.name} — {check.detail}")
    return 0 if all(item.passed for item in checks) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(verify()))
