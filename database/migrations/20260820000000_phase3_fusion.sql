begin;

create type vigia.evidence_strength as enum (
  'MUY_BAJA', 'BAJA', 'MEDIA', 'ALTA', 'MUY_ALTA'
);
create type vigia.data_quality_state as enum (
  'COMPLETA', 'PARCIAL', 'DEGRADADA', 'DESCONOCIDA'
);

create table vigia.fusion_runs (
  id uuid primary key default extensions.gen_random_uuid(),
  started_at timestamptz not null,
  completed_at timestamptz,
  as_of timestamptz not null,
  observation_from timestamptz,
  observation_to timestamptz,
  software_version text not null,
  code_commit text not null,
  request_id text not null,
  configuration jsonb not null,
  configuration_hash text not null,
  source_set text[] not null default '{}',
  observations_received bigint not null default 0 check (observations_received >= 0),
  observations_eligible bigint not null default 0 check (observations_eligible >= 0),
  candidates_found bigint not null default 0 check (candidates_found >= 0),
  incidents_created bigint not null default 0 check (incidents_created >= 0),
  incidents_updated bigint not null default 0 check (incidents_updated >= 0),
  state vigia.ingest_state not null default 'RUNNING',
  errors jsonb not null default '[]'::jsonb,
  constraint fusion_run_time_order check (completed_at is null or completed_at >= started_at),
  constraint fusion_run_observation_order check (
    observation_from is null or observation_to is null or observation_to >= observation_from
  )
);

create index fusion_runs_started_idx on vigia.fusion_runs (started_at desc);
create index fusion_runs_as_of_idx on vigia.fusion_runs (as_of desc);
create index fusion_runs_configuration_idx on vigia.fusion_runs (configuration_hash);
create index fusion_runs_request_idx on vigia.fusion_runs (request_id);

create table vigia.incident_candidates (
  id uuid primary key default extensions.gen_random_uuid(),
  fusion_run_id uuid not null references vigia.fusion_runs(id) on delete cascade,
  candidate_key text not null,
  first_observation_at timestamptz not null,
  last_observation_at timestamptz not null,
  centroid extensions.geography(Point, 4326) not null,
  spatial_extent_m double precision not null check (spatial_extent_m >= 0),
  observation_count integer not null check (observation_count > 0),
  platforms text[] not null,
  sensors text[] not null,
  source_families text[] not null,
  persistence jsonb not null,
  data_quality vigia.data_quality_state not null,
  recommendation vigia.incident_state not null,
  evidence_strength vigia.evidence_strength not null,
  reason_codes text[] not null,
  explanation jsonb not null,
  configuration_hash text not null,
  created_at timestamptz not null default now(),
  unique (fusion_run_id, candidate_key),
  constraint incident_candidate_time_order check (
    last_observation_at >= first_observation_at
  )
);

create index incident_candidates_centroid_gist
  on vigia.incident_candidates using gist (centroid);
create index incident_candidates_time_idx
  on vigia.incident_candidates (last_observation_at desc);

alter table vigia.fire_incidents
  add column observation_count integer not null default 0 check (observation_count >= 0),
  add column source_families text[] not null default '{}',
  add column evidence_strength vigia.evidence_strength,
  add column reason_codes text[] not null default '{}',
  add column explanation jsonb not null default '{}'::jsonb,
  add column persistence jsonb not null default '{}'::jsonb,
  add column fusion_data_quality vigia.data_quality_state not null default 'DESCONOCIDA',
  add column processed_at timestamptz,
  add column last_fusion_as_of timestamptz,
  add column configuration_hash text,
  add column rule_version text,
  add column stale boolean not null default false,
  add column inactive_at timestamptz;

create index fire_incidents_public_state_idx
  on vigia.fire_incidents (state, last_observation_at desc)
  where public_visible = true;

alter table vigia.incident_status_history
  add column previous_state vigia.incident_state,
  add column configuration_hash text,
  add column software_version text,
  add column rule_version text,
  add column fusion_run_id uuid references vigia.fusion_runs(id);

create index incident_status_history_fusion_run_idx
  on vigia.incident_status_history (fusion_run_id)
  where fusion_run_id is not null;

create table vigia.fusion_run_incidents (
  fusion_run_id uuid not null references vigia.fusion_runs(id) on delete cascade,
  incident_id uuid not null references vigia.fire_incidents(id) on delete cascade,
  candidate_id uuid not null references vigia.incident_candidates(id) on delete cascade,
  action text not null check (action in ('created', 'updated', 'unchanged')),
  primary key (fusion_run_id, incident_id)
);

create index fusion_run_incidents_incident_idx
  on vigia.fusion_run_incidents (incident_id);

create table vigia.incident_context_evidence (
  incident_id uuid not null references vigia.fire_incidents(id) on delete cascade,
  entity_type text not null check (
    entity_type in ('weather_observation', 'known_heat_source', 'controlled_burn')
  ),
  entity_id uuid not null,
  evidence_role text not null check (evidence_role in ('contradicting', 'context')),
  reason_codes text[] not null default '{}',
  rule_version text not null,
  added_at timestamptz not null default now(),
  primary key (incident_id, entity_type, entity_id)
);

create index incident_context_evidence_entity_idx
  on vigia.incident_context_evidence (entity_type, entity_id);

create table vigia.known_heat_sources (
  id uuid primary key default extensions.gen_random_uuid(),
  external_id text,
  name text not null,
  category text not null,
  location extensions.geography(Point, 4326) not null,
  match_radius_m double precision not null check (match_radius_m > 0),
  source_id uuid references vigia.sources(id),
  source_uri text not null,
  license_uri text,
  valid_from timestamptz,
  valid_to timestamptz,
  quality jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (source_id, external_id)
);

create index known_heat_sources_location_gist
  on vigia.known_heat_sources using gist (location);

create table vigia.controlled_burn_context (
  id uuid primary key default extensions.gen_random_uuid(),
  external_id text not null,
  source_id uuid not null references vigia.sources(id),
  geometry extensions.geometry(Geometry, 4326) not null,
  authorized_from timestamptz not null,
  authorized_to timestamptz not null,
  status text not null,
  source_uri text not null,
  quality jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (source_id, external_id),
  constraint controlled_burn_time_order check (authorized_to >= authorized_from)
);

create index controlled_burn_context_geometry_gist
  on vigia.controlled_burn_context using gist (geometry);
create index controlled_burn_context_time_idx
  on vigia.controlled_burn_context (authorized_from, authorized_to);

-- Phase 3 tables are internal. The backend API is the only public trust boundary.
alter table vigia.fusion_runs enable row level security;
alter table vigia.fusion_runs force row level security;
alter table vigia.incident_candidates enable row level security;
alter table vigia.incident_candidates force row level security;
alter table vigia.fusion_run_incidents enable row level security;
alter table vigia.fusion_run_incidents force row level security;
alter table vigia.incident_context_evidence enable row level security;
alter table vigia.incident_context_evidence force row level security;
alter table vigia.known_heat_sources enable row level security;
alter table vigia.known_heat_sources force row level security;
alter table vigia.controlled_burn_context enable row level security;
alter table vigia.controlled_burn_context force row level security;

revoke all on table
  vigia.fusion_runs,
  vigia.incident_candidates,
  vigia.fusion_run_incidents,
  vigia.incident_context_evidence,
  vigia.known_heat_sources,
  vigia.controlled_burn_context
from public, anon, authenticated;

commit;
