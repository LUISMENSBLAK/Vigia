from pathlib import Path

MIGRATION = Path("database/migrations/20260816000000_initial_vigia.sql")
PHASE3_MIGRATION = Path("database/migrations/20260820000000_phase3_fusion.sql")
PHASE4_MIGRATION = Path("database/migrations/20260820010000_phase4_geospatial.sql")
PHASE4B_MIGRATION = Path("database/migrations/20260820020000_phase4b_real_geospatial.sql")
PHASE5_MIGRATION = Path("database/migrations/20260820030000_phase5_national_risk.sql")
PHASE6_MIGRATION = Path("database/migrations/20260820040000_phase6_historical_replay.sql")
PHASE6_HARDENING = Path(
    "database/migrations/20260820040100_phase6_replay_immutability.sql"
)


def migration_sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").casefold()


def phase3_sql() -> str:
    return PHASE3_MIGRATION.read_text(encoding="utf-8").casefold()


def phase4_sql() -> str:
    return PHASE4_MIGRATION.read_text(encoding="utf-8").casefold()


def phase4b_sql() -> str:
    return PHASE4B_MIGRATION.read_text(encoding="utf-8").casefold()


def phase5_sql() -> str:
    return PHASE5_MIGRATION.read_text(encoding="utf-8").casefold()


def phase6_sql() -> str:
    return PHASE6_MIGRATION.read_text(encoding="utf-8").casefold()


def phase6_hardening_sql() -> str:
    return PHASE6_HARDENING.read_text(encoding="utf-8").casefold()


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


def test_phase3_adds_fusion_provenance_and_idempotent_candidates() -> None:
    sql = phase3_sql()
    assert "create table vigia.fusion_runs" in sql
    assert "configuration_hash text not null" in sql
    assert "create table vigia.incident_candidates" in sql
    assert "unique (fusion_run_id, candidate_key)" in sql
    assert "create table vigia.fusion_run_incidents" in sql
    assert "add column last_fusion_as_of timestamptz" in sql


def test_phase3_preserves_evidence_roles_and_immutable_history() -> None:
    sql = phase3_sql()
    assert "create table vigia.incident_context_evidence" in sql
    assert "evidence_role in ('contradicting', 'context')" in sql
    assert "add column previous_state vigia.incident_state" in sql
    assert "add column fusion_run_id uuid references vigia.fusion_runs" in sql


def test_phase3_prepares_empty_real_context_tables_without_seed_data() -> None:
    sql = phase3_sql()
    assert "create table vigia.known_heat_sources" in sql
    assert "create table vigia.controlled_burn_context" in sql
    assert "insert into vigia.known_heat_sources" not in sql
    assert "insert into vigia.controlled_burn_context" not in sql


def test_phase3_internal_tables_are_forced_behind_rls() -> None:
    sql = phase3_sql()
    for table in (
        "fusion_runs",
        "incident_candidates",
        "fusion_run_incidents",
        "incident_context_evidence",
        "known_heat_sources",
        "controlled_burn_context",
    ):
        assert f"alter table vigia.{table} enable row level security" in sql
        assert f"alter table vigia.{table} force row level security" in sql
    assert "from public, anon, authenticated" in sql


def test_phase4_catalogue_preserves_resolution_time_and_provenance() -> None:
    sql = phase4_sql()
    assert "create table vigia.geospatial_products" in sql
    for field in (
        "source_resolution_m",
        "output_resolution_m",
        "observed_at",
        "processed_at",
        "input_hashes",
        "output_hash",
        "configuration_hash",
        "algorithm",
        "provenance_id",
    ):
        assert field in sql
    assert "availability <> 'available'" in sql


def test_phase4_supports_national_administration_without_seeded_boundaries() -> None:
    sql = phase4_sql()
    assert "create table vigia.administrative_areas" in sql
    for level in ("country", "autonomous_community", "province", "municipality"):
        assert f"'{level}'" in sql
    assert "insert into vigia.administrative_areas" not in sql


def test_phase4_manifest_is_idempotent_and_never_stores_tokens() -> None:
    sql = phase4_sql()
    assert "create table vigia.download_manifests" in sql
    assert "unique (source_id, product_id, aoi_hash)" in sql
    assert "checksum_sha256" in sql
    assert "token" not in sql


def test_phase4_private_tables_force_rls() -> None:
    sql = phase4_sql()
    for table in (
        "administrative_areas",
        "geospatial_products",
        "download_manifests",
        "geospatial_processing_runs",
    ):
        assert f"alter table vigia.{table} enable row level security" in sql
        assert f"alter table vigia.{table} force row level security" in sql


def test_phase4b_separates_service_health_from_product_freshness() -> None:
    sql = phase4b_sql()
    for field in (
        "last_success_at",
        "last_product_at",
        "last_ingest_at",
        "check_interval_seconds",
        "product_freshness_seconds",
    ):
        assert field in sql
    assert "service_check_overdue" in sql
    assert "data_freshness" in sql


def test_phase4b_land_cover_and_product_lifecycle_stay_private() -> None:
    sql = phase4b_sql()
    assert "create table vigia.land_cover_features" in sql
    assert "alter table vigia.land_cover_features enable row level security" in sql
    assert "alter table vigia.land_cover_features force row level security" in sql
    for field in ("published_at", "invalidated_at", "superseded_by", "render_hint"):
        assert field in sql


def test_phase5_risk_contract_is_non_probabilistic_and_temporal() -> None:
    sql = phase5_sql()
    assert "create table vigia.risk_runs" in sql
    assert "experimental_index between 0 and 100" in sql
    assert "create type vigia.risk_mode" in sql
    assert "input_snapshot_hash" in sql
    assert "force row level security" in sql
    assert "risk_score double precision not null" not in sql


def test_phase6_separates_reference_truth_from_replay_inputs() -> None:
    sql = phase6_sql()
    assert "create table vigia.historical_fire_references" in sql
    assert "create table vigia.historical_fire_perimeters" in sql
    assert "create table vigia.replay_inputs" in sql
    replay_inputs = sql.split("create table vigia.replay_inputs", 1)[1].split(
        "create table vigia.replay_runs", 1
    )[0]
    assert "historical_fire_id" not in replay_inputs
    assert "perimeter" not in replay_inputs
    assert "available_at >= observed_at" in replay_inputs
    assert "historical_fire_perimeters_geometry_gist" in sql
    assert "provenance jsonb not null" in sql


def test_phase6_replay_runs_are_isolated_idempotent_and_reproducible() -> None:
    sql = phase6_sql()
    assert "run_hash text not null unique" in sql
    assert "code_commit text not null" in sql
    assert "case_manifest_hash" in sql
    assert "input_snapshot_hash" in sql
    assert "live_state_mutated boolean not null default false" in sql
    assert "check (live_state_mutated = false)" in sql


def test_phase6_private_tables_force_rls() -> None:
    sql = phase6_sql()
    for table in (
        "historical_fire_references",
        "historical_fire_timestamps",
        "historical_fire_perimeters",
        "replay_cases",
        "replay_inputs",
        "replay_runs",
        "replay_steps",
    ):
        assert f"alter table vigia.{table} enable row level security" in sql
        assert f"alter table vigia.{table} force row level security" in sql


def test_phase6_frozen_manifest_is_database_enforced() -> None:
    sql = phase6_hardening_sql()
    assert "prevent_frozen_replay_case_update" in sql
    assert "replay_cases_immutable_when_frozen" in sql
    assert "to_jsonb(new) - 'updated_at'" in sql
    assert "update vigia.replay_cases set frozen = true" in sql
