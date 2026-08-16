begin;

create schema if not exists extensions;
create extension if not exists postgis with schema extensions;
create extension if not exists pgcrypto with schema extensions;

create schema if not exists vigia;
create schema if not exists api;

revoke all on schema vigia from public, anon, authenticated;
revoke all on schema api from public, anon, authenticated;
grant usage on schema api to anon, authenticated;

create type vigia.source_state as enum ('OPERATIVO', 'DEGRADADO', 'SIN_DATOS', 'ERROR');
create type vigia.ingest_state as enum ('RUNNING', 'SUCCEEDED', 'PARTIAL', 'FAILED');
create type vigia.incident_state as enum (
  'SIN_EVIDENCIA', 'VIGILANCIA', 'ANOMALIA', 'POSIBLE_IGNICION',
  'PROBABLE_INCENDIO', 'INCENDIO_CONFIRMADO', 'DESCARTADO'
);
create type vigia.perimeter_type as enum ('observed', 'predicted');
create type vigia.weather_value_type as enum ('OBSERVADO', 'INTERPOLADO', 'PRONOSTICADO');

create table vigia.sources (
  id uuid primary key default extensions.gen_random_uuid(),
  code text not null unique,
  name text not null,
  provider text not null,
  dataset_version text,
  license_uri text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table vigia.source_health (
  source_id uuid primary key references vigia.sources(id) on delete cascade,
  state vigia.source_state not null default 'SIN_DATOS',
  checked_at timestamptz not null,
  last_observed_at timestamptz,
  last_received_at timestamptz,
  latency_seconds integer check (latency_seconds is null or latency_seconds >= 0),
  error_code text,
  detail text not null,
  is_public boolean not null default true,
  constraint source_health_timestamps_ordered check (
    last_observed_at is null or last_received_at is null or last_received_at >= last_observed_at
  )
);

create table vigia.ingest_runs (
  id uuid primary key default extensions.gen_random_uuid(),
  source_id uuid not null references vigia.sources(id),
  state vigia.ingest_state not null,
  started_at timestamptz not null,
  finished_at timestamptz,
  records_received bigint not null default 0 check (records_received >= 0),
  records_written bigint not null default 0 check (records_written >= 0),
  errors jsonb not null default '[]'::jsonb,
  software_version text not null,
  request_id text,
  configuration_hash text not null,
  constraint ingest_finished_after_start check (finished_at is null or finished_at >= started_at)
);

create index ingest_runs_source_started_idx on vigia.ingest_runs (source_id, started_at desc);
create index ingest_runs_running_idx on vigia.ingest_runs (started_at) where state = 'RUNNING';

create table vigia.satellite_products (
  id uuid primary key default extensions.gen_random_uuid(),
  source_id uuid not null references vigia.sources(id),
  ingest_run_id uuid references vigia.ingest_runs(id),
  external_id text not null,
  sensing_started_at timestamptz not null,
  sensing_ended_at timestamptz,
  available_at timestamptz,
  received_at timestamptz not null,
  footprint extensions.geometry(MultiPolygon, 4326),
  bbox extensions.geometry(Polygon, 4326),
  crs text not null,
  resolution_m double precision check (resolution_m is null or resolution_m > 0),
  quality jsonb not null default '{}'::jsonb,
  storage_uri text,
  checksum_sha256 text,
  metadata jsonb not null default '{}'::jsonb,
  unique (source_id, external_id)
);

create index satellite_products_footprint_gist on vigia.satellite_products using gist (footprint);
create index satellite_products_sensing_idx on vigia.satellite_products (sensing_started_at desc);

create table vigia.fire_observations (
  id uuid primary key default extensions.gen_random_uuid(),
  source_id uuid not null references vigia.sources(id),
  product_id uuid references vigia.satellite_products(id),
  ingest_run_id uuid not null references vigia.ingest_runs(id),
  external_id text,
  observed_at timestamptz not null,
  received_at timestamptz not null,
  location extensions.geography(Point, 4326) not null,
  footprint extensions.geometry(Polygon, 4326),
  sensor text not null,
  platform text not null,
  confidence_raw text,
  fire_probability double precision check (fire_probability between 0 and 1),
  brightness_kelvin double precision,
  frp_mw double precision,
  daynight text check (daynight is null or daynight in ('D', 'N')),
  quality jsonb not null default '{}'::jsonb,
  raw_properties jsonb not null,
  created_at timestamptz not null default now(),
  unique nulls not distinct (source_id, external_id)
);

create index fire_observations_location_gist on vigia.fire_observations using gist (location);
create index fire_observations_observed_idx on vigia.fire_observations (observed_at desc);
create index fire_observations_recent_source_idx on vigia.fire_observations (source_id, observed_at desc);

create table vigia.fire_incidents (
  id uuid primary key default extensions.gen_random_uuid(),
  code text not null unique,
  state vigia.incident_state not null default 'SIN_EVIDENCIA',
  centroid extensions.geography(Point, 4326) not null,
  first_signal_at timestamptz not null,
  last_observation_at timestamptz not null,
  calibrated_probability double precision check (calibrated_probability between 0 and 1),
  confidence_model_version text,
  data_quality jsonb not null default '{}'::jsonb,
  public_visible boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint incident_time_order check (last_observation_at >= first_signal_at),
  constraint confirmed_requires_model check (
    state <> 'INCENDIO_CONFIRMADO' or confidence_model_version is not null
  )
);

create index fire_incidents_centroid_gist on vigia.fire_incidents using gist (centroid);
create index fire_incidents_active_idx on vigia.fire_incidents (last_observation_at desc)
  where state not in ('DESCARTADO', 'SIN_EVIDENCIA');

create table vigia.observation_evidence (
  incident_id uuid not null references vigia.fire_incidents(id) on delete cascade,
  observation_id uuid not null references vigia.fire_observations(id) on delete restrict,
  evidence_role text not null check (evidence_role in ('confirming', 'contradicting', 'context')),
  weight_model_version text,
  added_at timestamptz not null default now(),
  primary key (incident_id, observation_id)
);

create table vigia.incident_status_history (
  id bigint generated always as identity primary key,
  incident_id uuid not null references vigia.fire_incidents(id),
  state vigia.incident_state not null,
  changed_at timestamptz not null,
  changed_by text not null,
  reason text not null,
  evidence_snapshot jsonb not null,
  model_version text,
  commit_sha text
);

create index incident_status_history_incident_idx on vigia.incident_status_history (incident_id, changed_at);

create table vigia.incident_perimeters (
  id uuid primary key default extensions.gen_random_uuid(),
  incident_id uuid not null references vigia.fire_incidents(id),
  type vigia.perimeter_type not null,
  valid_at timestamptz not null,
  horizon_minutes integer check (horizon_minutes is null or horizon_minutes >= 0),
  source_id uuid references vigia.sources(id),
  confidence double precision check (confidence between 0 and 1),
  probability_band text check (probability_band is null or probability_band in ('P10', 'P50', 'P90')),
  geometry extensions.geometry(MultiPolygon, 4326) not null,
  crs text not null default 'EPSG:4326',
  model_version text,
  is_experimental boolean not null default false,
  created_at timestamptz not null default now()
);

create index incident_perimeters_geometry_gist on vigia.incident_perimeters using gist (geometry);
create index incident_perimeters_incident_valid_idx on vigia.incident_perimeters (incident_id, valid_at desc);

create table vigia.weather_observations (
  id uuid primary key default extensions.gen_random_uuid(),
  source_id uuid not null references vigia.sources(id),
  station_code text,
  observed_at timestamptz not null,
  received_at timestamptz not null,
  location extensions.geography(Point, 4326) not null,
  value_type vigia.weather_value_type not null,
  temperature_c double precision,
  relative_humidity_pct double precision check (relative_humidity_pct between 0 and 100),
  wind_speed_ms double precision check (wind_speed_ms is null or wind_speed_ms >= 0),
  wind_direction_deg double precision check (wind_direction_deg is null or wind_direction_deg between 0 and 360),
  gust_ms double precision check (gust_ms is null or gust_ms >= 0),
  precipitation_mm double precision check (precipitation_mm is null or precipitation_mm >= 0),
  pressure_hpa double precision,
  quality jsonb not null default '{}'::jsonb
);

create index weather_observations_location_gist on vigia.weather_observations using gist (location);
create index weather_observations_time_idx on vigia.weather_observations (observed_at desc);

create table vigia.weather_forecasts (
  id uuid primary key default extensions.gen_random_uuid(),
  source_id uuid not null references vigia.sources(id),
  issued_at timestamptz not null,
  valid_at timestamptz not null,
  location extensions.geography(Point, 4326) not null,
  location_key text not null,
  model_name text not null,
  model_run text not null,
  variables jsonb not null,
  quality jsonb not null default '{}'::jsonb,
  unique (source_id, model_run, valid_at, location_key)
);

create index weather_forecasts_location_gist on vigia.weather_forecasts using gist (location);
create index weather_forecasts_valid_idx on vigia.weather_forecasts (valid_at);

create table vigia.terrain_cells (
  id bigint generated always as identity primary key,
  cell_id text not null unique,
  geometry extensions.geometry(Polygon, 4326) not null,
  elevation_m double precision,
  slope_deg double precision,
  aspect_deg double precision,
  roughness double precision,
  resolution_m double precision not null check (resolution_m > 0),
  product_uri text not null,
  checksum_sha256 text not null,
  source_version text not null,
  valid_at timestamptz not null
);

create index terrain_cells_geometry_gist on vigia.terrain_cells using gist (geometry);

create table vigia.vegetation_cells (
  id bigint generated always as identity primary key,
  cell_id text not null,
  geometry extensions.geometry(Polygon, 4326) not null,
  observed_at timestamptz not null,
  ndvi double precision,
  ndmi double precision,
  nbr double precision,
  canopy_height_m double precision,
  fuel_proxy double precision,
  source_version text not null,
  quality jsonb not null default '{}'::jsonb,
  unique (cell_id, observed_at)
);

create index vegetation_cells_geometry_gist on vigia.vegetation_cells using gist (geometry);
create index vegetation_cells_observed_idx on vigia.vegetation_cells (observed_at desc);

create table vigia.model_versions (
  id uuid primary key default extensions.gen_random_uuid(),
  model_name text not null,
  version text not null,
  task text not null,
  commit_sha text not null,
  artifact_uri text not null,
  artifact_hash text not null,
  dataset_hash text not null,
  configuration jsonb not null,
  seed bigint not null,
  status text not null check (status in ('research', 'validation', 'approved', 'retired')),
  created_at timestamptz not null default now(),
  unique (model_name, version)
);

create table vigia.risk_predictions (
  id uuid primary key default extensions.gen_random_uuid(),
  model_version_id uuid not null references vigia.model_versions(id),
  valid_at timestamptz not null,
  geometry extensions.geometry(Polygon, 4326) not null,
  risk_score double precision not null check (risk_score between 0 and 1),
  level text not null,
  confidence_interval numrange,
  top_factors jsonb not null,
  data_quality jsonb not null,
  provenance_id uuid,
  created_at timestamptz not null default now()
);

create index risk_predictions_geometry_gist on vigia.risk_predictions using gist (geometry);
create index risk_predictions_valid_idx on vigia.risk_predictions (valid_at desc);

create table vigia.forecast_ensembles (
  id uuid primary key default extensions.gen_random_uuid(),
  incident_id uuid not null references vigia.fire_incidents(id),
  model_version_id uuid not null references vigia.model_versions(id),
  started_at timestamptz not null,
  completed_at timestamptz,
  simulation_count integer not null check (simulation_count > 0),
  seed bigint not null,
  configuration jsonb not null,
  input_snapshot_hash text not null,
  experimental boolean not null default true
);

create table vigia.spread_predictions (
  id uuid primary key default extensions.gen_random_uuid(),
  ensemble_id uuid not null references vigia.forecast_ensembles(id),
  valid_at timestamptz not null,
  horizon_minutes integer not null check (horizon_minutes in (15, 30, 60, 120, 240, 360)),
  probability_band text not null check (probability_band in ('P10', 'P50', 'P90')),
  perimeter extensions.geometry(MultiPolygon, 4326) not null,
  affected_area_probability_uri text,
  created_at timestamptz not null default now(),
  unique (ensemble_id, horizon_minutes, probability_band)
);

create index spread_predictions_perimeter_gist on vigia.spread_predictions using gist (perimeter);

create table vigia.historical_fires (
  id uuid primary key default extensions.gen_random_uuid(),
  external_id text,
  name text,
  started_at timestamptz not null,
  ended_at timestamptz,
  origin extensions.geography(Point, 4326),
  final_perimeter extensions.geometry(MultiPolygon, 4326),
  source_id uuid not null references vigia.sources(id),
  license_uri text,
  quality jsonb not null default '{}'::jsonb
);

create index historical_fires_perimeter_gist on vigia.historical_fires using gist (final_perimeter);

create table vigia.validation_cases (
  id uuid primary key default extensions.gen_random_uuid(),
  historical_fire_id uuid references vigia.historical_fires(id),
  region_code text not null,
  split text not null check (split in ('train', 'validation', 'test')),
  replay_start_at timestamptz not null,
  replay_end_at timestamptz not null,
  dataset_hash text not null,
  leakage_checked boolean not null default false,
  constraint validation_case_time_order check (replay_end_at > replay_start_at)
);

create table vigia.validation_runs (
  id uuid primary key default extensions.gen_random_uuid(),
  model_version_id uuid not null references vigia.model_versions(id),
  started_at timestamptz not null,
  completed_at timestamptz,
  commit_sha text not null,
  dataset_hash text not null,
  temporal_range tstzrange not null,
  regions text[] not null,
  seed bigint not null,
  configuration jsonb not null,
  sample_size integer check (sample_size is null or sample_size >= 0),
  reproducible boolean not null default false
);

create table vigia.model_metrics (
  id bigint generated always as identity primary key,
  validation_run_id uuid not null references vigia.validation_runs(id),
  metric_name text not null,
  metric_value double precision not null,
  confidence_interval numrange,
  sample_size integer not null check (sample_size > 0),
  subgroup jsonb not null default '{}'::jsonb,
  unique (validation_run_id, metric_name, subgroup)
);

create table vigia.alerts (
  id uuid primary key default extensions.gen_random_uuid(),
  incident_id uuid not null references vigia.fire_incidents(id),
  created_at timestamptz not null,
  severity text not null,
  status text not null,
  audience text not null,
  content jsonb not null,
  acknowledged_at timestamptz,
  acknowledged_by uuid
);

create table vigia.data_provenance (
  id uuid primary key default extensions.gen_random_uuid(),
  entity_type text not null,
  entity_id uuid not null,
  dataset text not null,
  dataset_version text not null,
  source_timestamp timestamptz not null,
  transformation text not null,
  code_commit text not null,
  parameters jsonb not null,
  input_hashes text[] not null,
  output_hash text not null,
  created_at timestamptz not null default now()
);

create index data_provenance_entity_idx on vigia.data_provenance (entity_type, entity_id);

alter table vigia.risk_predictions
  add constraint risk_predictions_provenance_fk
  foreign key (provenance_id) references vigia.data_provenance(id);

create table vigia.audit_log (
  id bigint generated always as identity primary key,
  occurred_at timestamptz not null default now(),
  actor_type text not null,
  actor_id text,
  action text not null,
  entity_type text not null,
  entity_id text,
  request_id text,
  ingest_id uuid,
  model_run_id uuid,
  details jsonb not null default '{}'::jsonb
);

create index audit_log_occurred_idx on vigia.audit_log (occurred_at desc);
create index audit_log_request_idx on vigia.audit_log (request_id) where request_id is not null;

-- Defense in depth: all internal tables use RLS, with no broad client policies.
do $$
declare table_name text;
begin
  for table_name in
    select tablename from pg_tables where schemaname = 'vigia'
  loop
    execute format('alter table vigia.%I enable row level security', table_name);
    execute format('alter table vigia.%I force row level security', table_name);
  end loop;
end $$;

-- The public viewer can only read explicitly public source-health rows.
create policy source_health_public_read
  on vigia.source_health for select
  to anon, authenticated
  using (is_public = true);

create policy sources_public_read
  on vigia.sources for select
  to anon, authenticated
  using (true);

grant usage on schema vigia to anon, authenticated;
grant select on table vigia.sources, vigia.source_health to anon, authenticated;

create view api.source_health
with (security_invoker = true)
as
select
  s.code,
  s.name,
  h.state,
  h.checked_at,
  h.last_observed_at,
  h.last_received_at,
  h.latency_seconds,
  h.detail
from vigia.source_health h
join vigia.sources s on s.id = h.source_id
where h.is_public = true;

revoke all on api.source_health from public;
grant select on api.source_health to anon, authenticated;

-- Workers are expected to connect using a server-side database role. No browser role receives writes.
revoke insert, update, delete on all tables in schema vigia from anon, authenticated;
alter default privileges for role postgres in schema vigia
  revoke select, insert, update, delete on tables from anon, authenticated, public;
alter default privileges for role postgres in schema vigia
  revoke execute on functions from anon, authenticated, public;
alter default privileges for role postgres in schema vigia
  revoke usage, select on sequences from anon, authenticated, public;

commit;
