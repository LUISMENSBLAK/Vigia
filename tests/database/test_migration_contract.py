from pathlib import Path

MIGRATION = Path("database/migrations/20260816000000_initial_vigia.sql")


def migration_sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").casefold()


def test_migration_keeps_private_and_api_schemas() -> None:
    sql = migration_sql()
    assert "create schema if not exists vigia" in sql
    assert "create schema if not exists api" in sql
    assert "create extension if not exists postgis" in sql
    assert "create extension if not exists pgcrypto" in sql


def test_all_internal_tables_are_forced_behind_rls() -> None:
    sql = migration_sql()
    assert "alter table vigia.%i enable row level security" in sql
    assert "alter table vigia.%i force row level security" in sql
    assert "revoke insert, update, delete on all tables in schema vigia" in sql
    assert "grant select on table vigia.sources, vigia.source_health" in sql


def test_browser_roles_never_receive_privileged_access() -> None:
    sql = migration_sql()
    assert "grant usage on schema api to anon, authenticated" in sql
    assert "with (security_invoker = true)" in sql
    assert "grant all" not in sql
    assert "service_role" not in sql


def test_fire_observations_have_spatial_temporal_and_idempotency_guards() -> None:
    sql = migration_sql()
    assert "location extensions.geography(point, 4326) not null" in sql
    assert "fire_observations_location_gist" in sql
    assert "fire_observations_observed_idx" in sql
    assert "external_id text not null" in sql
    assert "unique (source_id, external_id)" in sql
    assert "received_at >= observed_at" in sql


def test_runtime_queries_have_matching_temporal_indexes() -> None:
    sql = migration_sql()
    assert "ingest_runs_started_idx" in sql
    assert "(entity_type, entity_id, created_at desc)" in sql


def test_required_source_catalogue_is_explicit() -> None:
    sql = migration_sql()
    for code in (
        "nasa_firms_viirs_noaa20_nrt",
        "nasa_firms_viirs_noaa21_nrt",
        "nasa_firms_viirs_snpp_nrt",
        "nasa_firms_modis_nrt",
        "aemet_open_data",
        "eumetsat_mtg_fci_afm",
        "copernicus_sentinel_1",
        "copernicus_sentinel_2",
        "copernicus_sentinel_3",
        "pnoa_cnig",
    ):
        assert code in sql
