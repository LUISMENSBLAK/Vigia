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
    try:
        connection = await asyncpg.connect(
            settings.SUPABASE_DB_URL.get_secret_value(), timeout=20, command_timeout=60
        )
    except (asyncpg.InvalidPasswordError, OSError, TimeoutError):
        print("NO VERIFICADO: conexión PostgreSQL no disponible.")
        return 1
    checks: list[Check] = []
    try:
        tables = await connection.fetchval(
            """
            select count(*) from information_schema.tables
            where table_schema = 'vigia' and table_name in ('risk_runs', 'risk_predictions')
            """
        )
        checks.append(Check("tablas", tables == 2, f"{tables}/2"))
        columns = await connection.fetchval(
            """
            select count(*) from information_schema.columns
            where table_schema = 'vigia' and table_name = 'risk_predictions'
              and column_name in (
                'experimental_index', 'component_scores', 'reason_codes',
                'missing_components', 'as_of', 'horizon_hours', 'output_hash'
              )
            """
        )
        checks.append(Check("columnas de riesgo", columns == 7, f"{columns}/7"))
        constraints = await connection.fetchval(
            """
            select count(*) from pg_constraint constraint_row
            join pg_class relation on relation.oid = constraint_row.conrelid
            join pg_namespace namespace on namespace.oid = relation.relnamespace
            where namespace.nspname = 'vigia'
              and relation.relname in ('risk_runs', 'risk_predictions')
            """
        )
        checks.append(Check("constraints", constraints >= 12, f"{constraints} encontradas"))
        indexes = await connection.fetchval(
            """
            select count(*) from pg_indexes where schemaname = 'vigia'
              and indexname in (
                'risk_runs_aoi_gist', 'risk_runs_time_idx', 'risk_runs_state_idx',
                'risk_predictions_prediction_key_idx', 'risk_predictions_centroid_gist',
                'risk_predictions_mode_time_idx'
              )
            """
        )
        checks.append(Check("índices", indexes == 6, f"{indexes}/6"))
        rls = await connection.fetchval(
            """
            select count(*) from pg_class relation
            join pg_namespace namespace on namespace.oid = relation.relnamespace
            where namespace.nspname = 'vigia'
              and relation.relname in ('risk_runs', 'risk_predictions')
              and relation.relrowsecurity and relation.relforcerowsecurity
            """
        )
        checks.append(Check("RLS forzado", rls == 2, f"{rls}/2"))
        browser_access = await connection.fetchval(
            """
            select bool_or(
              has_table_privilege(role_name, 'vigia.risk_runs', 'select')
              or has_table_privilege(role_name, 'vigia.risk_predictions', 'select')
            ) from unnest(array['anon', 'authenticated']) as role_name
            """
        )
        checks.append(Check("grants privados", browser_access is False, "anon/authenticated"))
        layer_constraint = await connection.fetchval(
            """
            select pg_get_constraintdef(oid) like '%RISK_BASELINE%'
            from pg_constraint where conname = 'geospatial_products_layer_check'
            """
        )
        checks.append(Check("catálogo raster riesgo", bool(layer_constraint), "RISK_BASELINE"))
    finally:
        await connection.close()
    for check in checks:
        print(f"{'GREEN' if check.passed else 'ERROR'}: {check.name} — {check.detail}")
    return 0 if all(check.passed for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(verify()))
