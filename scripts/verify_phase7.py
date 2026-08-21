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
        settings.SUPABASE_DB_URL.get_secret_value(), timeout=20, command_timeout=90
    )
    tables_under_test = (
        "validation_dataset_versions",
        "validation_split_manifests",
        "validation_dataset_members",
        "validation_control_windows",
        "validation_engine_versions",
        "validation_metric_results",
        "validation_matches",
        "validation_errors",
        "validation_test_access_log",
    )
    checks: list[Check] = []
    try:
        tables = await connection.fetchval(
            """
            select count(*) from information_schema.tables
            where table_schema = 'vigia' and table_name = any($1::text[])
            """,
            tables_under_test,
        )
        checks.append(Check("tablas Fase 7", tables == 9, f"{tables}/9"))
        rls = await connection.fetchval(
            """
            select count(*) from pg_class relation
            join pg_namespace namespace on namespace.oid = relation.relnamespace
            where namespace.nspname = 'vigia'
              and relation.relname = any($1::text[])
              and relation.relrowsecurity and relation.relforcerowsecurity
            """,
            (*tables_under_test, "validation_runs"),
        )
        checks.append(Check("RLS forzado", rls == 10, f"{rls}/10"))
        grants = await connection.fetchval(
            """
            select count(*) from information_schema.role_table_grants
            where table_schema = 'vigia' and table_name = any($1::text[])
              and grantee in ('anon', 'authenticated')
              and privilege_type in ('INSERT', 'UPDATE', 'DELETE')
            """,
            (*tables_under_test, "validation_runs"),
        )
        checks.append(Check("sin escritura cliente", grants == 0, f"{grants} grants"))
        triggers = await connection.fetchval(
            """
            select count(*) from pg_trigger where not tgisinternal and tgname in (
              'validation_datasets_immutable', 'validation_splits_immutable',
              'validation_engines_immutable', 'validation_runs_immutable_when_published',
              'validation_test_access_immutable', 'validation_test_run_requires_audit'
            )
            """
        )
        checks.append(Check("inmutabilidad y TEST guard", triggers == 6, f"{triggers}/6"))
        test_runs_without_audit = await connection.fetchval(
            """
            select count(*) from vigia.validation_runs
            where split_role = 'TEST' and test_access_audit_id is null
            """
        )
        checks.append(
            Check(
                "TEST auditado",
                test_runs_without_audit == 0,
                f"{test_runs_without_audit} runs sin auditoría",
            )
        )
        mutable = await connection.fetchval(
            """
            select
              (select count(*) from vigia.validation_dataset_versions where not frozen)
              + (select count(*) from vigia.validation_split_manifests where not frozen)
              + (select count(*) from vigia.validation_engine_versions where not frozen)
            """
        )
        checks.append(Check("artefactos congelados", mutable == 0, f"{mutable} mutables"))
    finally:
        await connection.close()
    for check in checks:
        print(f"{'GREEN' if check.passed else 'ERROR'}: {check.name} — {check.detail}")
    return 0 if all(item.passed for item in checks) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(verify()))
