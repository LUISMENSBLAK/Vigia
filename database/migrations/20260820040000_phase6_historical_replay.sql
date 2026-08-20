begin;

create type vigia.timestamp_precision as enum ('DATE_ONLY', 'HOUR', 'MINUTE', 'EXACT', 'UNKNOWN');
create type vigia.reference_quality as enum ('HIGH', 'MEDIUM', 'LOW', 'UNKNOWN');
create type vigia.replay_case_kind as enum ('POSITIVE_REFERENCE', 'CONTROL_NO_KNOWN_FIRE');
create type vigia.replay_input_kind as enum (
  'THERMAL_OBSERVATION', 'WEATHER_OBSERVATION', 'SENTINEL_PRODUCT',
  'TERRAIN_PRODUCT', 'LAND_COVER_PRODUCT'
);

insert into vigia.sources (code, name, provider, dataset_version, license_uri, metadata)
values
  (
    'JCYL_HISTORICAL_FIRES', 'Incendios forestales de Castilla y León',
    'Junta de Castilla y León', 'continuous-publication', null,
    '{"dataset":"Incendios forestales","scope":"regional historical reference","license_status":"NO_VERIFICADO"}'::jsonb
  ),
  (
    'NASA_FIRMS_VIIRS_NOAA20_SP', 'NASA FIRMS VIIRS NOAA-20 Standard Processing',
    'NASA LANCE FIRMS', null,
    'https://www.earthdata.nasa.gov/engage/open-data-services-software-policies/data-use-guidance',
    '{"dataset":"VIIRS NOAA-20 375 m Active Fire","processing":"standard"}'::jsonb
  ),
  (
    'NASA_FIRMS_VIIRS_SNPP_SP', 'NASA FIRMS VIIRS SNPP Standard Processing',
    'NASA LANCE FIRMS', null,
    'https://www.earthdata.nasa.gov/engage/open-data-services-software-policies/data-use-guidance',
    '{"dataset":"VIIRS Suomi-NPP 375 m Active Fire","processing":"standard"}'::jsonb
  ),
  (
    'NASA_FIRMS_MODIS_SP', 'NASA FIRMS MODIS Standard Processing',
    'NASA LANCE FIRMS', '6.1',
    'https://www.earthdata.nasa.gov/engage/open-data-services-software-policies/data-use-guidance',
    '{"dataset":"MODIS Collection 6.1 Active Fire","processing":"standard"}'::jsonb
  )
on conflict (code) do nothing;

alter table vigia.historical_fires
  alter column started_at drop not null,
  add column event_key text,
  add column vigia_code text,
  add column region text,
  add column provinces text[] not null default '{}',
  add column municipality text,
  add column reference_quality vigia.reference_quality not null default 'UNKNOWN',
  add column canonical_metadata jsonb not null default '{}'::jsonb,
  add column created_at timestamptz not null default now(),
  add column updated_at timestamptz not null default now();

update vigia.historical_fires
set event_key = coalesce(external_id, id::text),
    vigia_code = coalesce(name, 'VIGIA-HIST-' || left(id::text, 12))
where event_key is null or vigia_code is null;

alter table vigia.historical_fires
  alter column event_key set not null,
  alter column vigia_code set not null,
  add constraint historical_fires_event_key_unique unique (event_key),
  add constraint historical_fires_vigia_code_unique unique (vigia_code);

create table vigia.historical_fire_references (
  id uuid primary key default extensions.gen_random_uuid(),
  historical_fire_id uuid not null references vigia.historical_fires(id) on delete cascade,
  source_id uuid not null references vigia.sources(id),
  external_record_id text not null,
  source_uri text not null,
  license_uri text,
  retrieved_at timestamptz not null,
  raw_checksum_sha256 text not null check (length(raw_checksum_sha256) = 64),
  original_record jsonb not null,
  normalized_metadata jsonb not null default '{}'::jsonb,
  reference_quality vigia.reference_quality not null,
  created_at timestamptz not null default now(),
  unique (source_id, external_record_id, raw_checksum_sha256)
);
create index historical_fire_references_event_idx
  on vigia.historical_fire_references (historical_fire_id, retrieved_at desc);

create table vigia.historical_fire_timestamps (
  id uuid primary key default extensions.gen_random_uuid(),
  reference_id uuid not null references vigia.historical_fire_references(id) on delete cascade,
  meaning text not null check (meaning in (
    'ignition_time', 'reported_time', 'detected_time', 'official_start_time',
    'controlled_time', 'extinguished_time', 'reference_time'
  )),
  instant timestamptz,
  calendar_date date,
  precision vigia.timestamp_precision not null,
  timezone_name text,
  quality jsonb not null default '{}'::jsonb,
  unique (reference_id, meaning, precision, instant, calendar_date),
  constraint historical_timestamp_representation check (
    (precision = 'DATE_ONLY' and calendar_date is not null and instant is null)
    or (precision = 'UNKNOWN' and calendar_date is null and instant is null)
    or (precision in ('HOUR', 'MINUTE', 'EXACT') and instant is not null and calendar_date is null)
  )
);
create index historical_fire_timestamps_time_idx
  on vigia.historical_fire_timestamps (instant) where instant is not null;

create table vigia.historical_fire_perimeters (
  id uuid primary key default extensions.gen_random_uuid(),
  historical_fire_id uuid not null references vigia.historical_fires(id) on delete cascade,
  reference_id uuid not null references vigia.historical_fire_references(id) on delete cascade,
  external_id text not null,
  geometry extensions.geometry(MultiPolygon, 4326) not null,
  reference_at timestamptz,
  reference_date date,
  temporal_precision vigia.timestamp_precision not null,
  area_ha double precision check (area_ha is null or area_ha >= 0),
  original_crs text not null,
  resolution_m double precision check (resolution_m is null or resolution_m > 0),
  acquisition_method text,
  provenance jsonb not null,
  created_at timestamptz not null default now(),
  unique (reference_id, external_id),
  constraint historical_perimeter_time_representation check (
    (temporal_precision = 'DATE_ONLY' and reference_date is not null and reference_at is null)
    or (temporal_precision = 'UNKNOWN' and reference_date is null and reference_at is null)
    or (temporal_precision in ('HOUR', 'MINUTE', 'EXACT') and reference_at is not null and reference_date is null)
  )
);
create index historical_fire_perimeters_geometry_gist
  on vigia.historical_fire_perimeters using gist (geometry);

create table vigia.replay_cases (
  id uuid primary key default extensions.gen_random_uuid(),
  case_key text not null unique,
  historical_fire_id uuid references vigia.historical_fires(id),
  kind vigia.replay_case_kind not null,
  aoi extensions.geometry(MultiPolygon, 4326) not null,
  replay_start timestamptz not null,
  replay_end timestamptz not null,
  time_step_minutes integer not null check (time_step_minutes between 1 and 1440),
  manifest jsonb not null,
  manifest_hash text not null unique check (length(manifest_hash) = 64),
  case_version text not null,
  selection_policy_version text not null,
  available_sources text[] not null,
  reference_sources text[] not null,
  sensor_availability jsonb not null,
  reference_quality vigia.reference_quality not null,
  frozen boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint replay_case_time_order check (replay_end > replay_start),
  constraint replay_positive_reference check (
    kind <> 'POSITIVE_REFERENCE' or historical_fire_id is not null
  )
);
create index replay_cases_aoi_gist on vigia.replay_cases using gist (aoi);
create index replay_cases_time_idx on vigia.replay_cases (replay_start, replay_end);

create table vigia.replay_inputs (
  id uuid primary key default extensions.gen_random_uuid(),
  case_id uuid not null references vigia.replay_cases(id) on delete cascade,
  input_key text not null,
  kind vigia.replay_input_kind not null,
  source_code text not null,
  observed_at timestamptz not null,
  available_at timestamptz not null,
  location extensions.geography(Point, 4326),
  payload jsonb not null,
  provenance jsonb not null,
  availability_basis text not null check (availability_basis in (
    'OBSERVED', 'PUBLISHED', 'RECEIVED', 'OBSERVATION_TIME_PROXY'
  )),
  quality_flags text[] not null default '{}',
  input_hash text not null check (length(input_hash) = 64),
  created_at timestamptz not null default now(),
  unique (case_id, input_key),
  unique (case_id, input_hash),
  constraint replay_input_time_order check (available_at >= observed_at)
);
create index replay_inputs_case_time_idx
  on vigia.replay_inputs (case_id, available_at, observed_at);
create index replay_inputs_location_gist
  on vigia.replay_inputs using gist (location) where location is not null;

create table vigia.replay_runs (
  id uuid primary key default extensions.gen_random_uuid(),
  case_id uuid not null references vigia.replay_cases(id),
  run_hash text not null unique check (length(run_hash) = 64),
  state vigia.ingest_state not null,
  code_commit text not null,
  engine_versions jsonb not null,
  configuration jsonb not null,
  configuration_hash text not null check (length(configuration_hash) = 64),
  case_manifest_hash text not null check (length(case_manifest_hash) = 64),
  input_snapshot_hash text not null check (length(input_snapshot_hash) = 64),
  started_at timestamptz not null,
  completed_at timestamptz,
  step_count integer not null check (step_count >= 0),
  completed_step integer not null default -1 check (completed_step >= -1),
  observations_processed integer not null default 0 check (observations_processed >= 0),
  wall_time_ms bigint check (wall_time_ms is null or wall_time_ms >= 0),
  approximate_peak_memory_bytes bigint check (
    approximate_peak_memory_bytes is null or approximate_peak_memory_bytes >= 0
  ),
  deterministic boolean not null default true,
  live_state_mutated boolean not null default false check (live_state_mutated = false),
  errors jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  constraint replay_run_time_order check (completed_at is null or completed_at >= started_at),
  constraint replay_run_step_progress check (completed_step < step_count or step_count = 0)
);
create index replay_runs_case_started_idx on vigia.replay_runs (case_id, started_at desc);
create index replay_runs_state_idx on vigia.replay_runs (state, started_at desc);

create table vigia.replay_steps (
  id uuid primary key default extensions.gen_random_uuid(),
  replay_run_id uuid not null references vigia.replay_runs(id) on delete cascade,
  step_index integer not null check (step_index >= 0),
  as_of timestamptz not null,
  visible_input_count integer not null check (visible_input_count >= 0),
  visible_observation_count integer not null check (visible_observation_count >= 0),
  candidate_count integer not null check (candidate_count >= 0),
  incidents jsonb not null,
  risk jsonb not null,
  availability jsonb not null,
  exclusion_counts jsonb not null,
  output_hash text not null check (length(output_hash) = 64),
  created_at timestamptz not null default now(),
  unique (replay_run_id, step_index),
  unique (replay_run_id, output_hash)
);
create index replay_steps_run_time_idx on vigia.replay_steps (replay_run_id, as_of);

alter table vigia.historical_fire_references enable row level security;
alter table vigia.historical_fire_references force row level security;
alter table vigia.historical_fire_timestamps enable row level security;
alter table vigia.historical_fire_timestamps force row level security;
alter table vigia.historical_fire_perimeters enable row level security;
alter table vigia.historical_fire_perimeters force row level security;
alter table vigia.replay_cases enable row level security;
alter table vigia.replay_cases force row level security;
alter table vigia.replay_inputs enable row level security;
alter table vigia.replay_inputs force row level security;
alter table vigia.replay_runs enable row level security;
alter table vigia.replay_runs force row level security;
alter table vigia.replay_steps enable row level security;
alter table vigia.replay_steps force row level security;

revoke all on
  vigia.historical_fires,
  vigia.historical_fire_references,
  vigia.historical_fire_timestamps,
  vigia.historical_fire_perimeters,
  vigia.replay_cases,
  vigia.replay_inputs,
  vigia.replay_runs,
  vigia.replay_steps
from public, anon, authenticated;

commit;
