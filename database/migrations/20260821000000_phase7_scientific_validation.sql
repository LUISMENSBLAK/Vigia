begin;

create type vigia.validation_split_role as enum ('DEVELOPMENT', 'VALIDATION', 'TEST');
create type vigia.validation_member_kind as enum (
  'POSITIVE_REFERENCE', 'NO_KNOWN_FIRE_CONTROL', 'HARD_NEGATIVE'
);
create type vigia.metric_availability as enum (
  'AVAILABLE', 'INSUFFICIENT_SAMPLE', 'NO_DISPONIBLE'
);

create table vigia.validation_dataset_versions (
  id uuid primary key default extensions.gen_random_uuid(),
  version text not null unique,
  dataset_hash text not null unique check (length(dataset_hash) = 64),
  manifest jsonb not null,
  sources jsonb not null,
  filters jsonb not null,
  selection_policy_version text not null,
  event_count integer not null check (event_count >= 0),
  control_count integer not null check (control_count >= 0),
  regions_covered text[] not null,
  years_covered integer[] not null,
  coverage_limitations text[] not null,
  frozen boolean not null default true check (frozen),
  created_at timestamptz not null,
  published_at timestamptz
);

create table vigia.validation_split_manifests (
  id uuid primary key default extensions.gen_random_uuid(),
  dataset_version_id uuid not null references vigia.validation_dataset_versions(id),
  version text not null unique,
  policy_version text not null,
  manifest jsonb not null,
  split_hash text not null unique check (length(split_hash) = 64),
  development_count integer not null check (development_count >= 0),
  validation_count integer not null check (validation_count >= 0),
  test_count integer not null check (test_count >= 0),
  leakage_checked boolean not null default false,
  test_frozen boolean not null default true check (test_frozen),
  frozen boolean not null default true check (frozen),
  created_at timestamptz not null
);
create index validation_splits_dataset_idx
  on vigia.validation_split_manifests (dataset_version_id, created_at desc);

create table vigia.validation_dataset_members (
  id uuid primary key default extensions.gen_random_uuid(),
  dataset_version_id uuid not null references vigia.validation_dataset_versions(id),
  split_manifest_id uuid not null references vigia.validation_split_manifests(id),
  member_key text not null,
  event_group_id text not null,
  kind vigia.validation_member_kind not null,
  split_role vigia.validation_split_role not null,
  historical_fire_id uuid references vigia.historical_fires(id),
  reference_quality vigia.reference_quality,
  reference_time timestamptz,
  reference_location extensions.geography(Point, 4326),
  metadata jsonb not null,
  created_at timestamptz not null default now(),
  unique (dataset_version_id, member_key)
);
create index validation_members_split_idx
  on vigia.validation_dataset_members (split_manifest_id, split_role, member_key);
create index validation_members_group_idx
  on vigia.validation_dataset_members (event_group_id, split_role);
create index validation_members_location_gist
  on vigia.validation_dataset_members using gist (reference_location)
  where reference_location is not null;

create table vigia.validation_control_windows (
  id uuid primary key default extensions.gen_random_uuid(),
  member_id uuid not null unique references vigia.validation_dataset_members(id) on delete cascade,
  aoi extensions.geometry(MultiPolygon, 4326) not null,
  evaluation_period tstzrange not null,
  area_km2 double precision not null check (area_km2 > 0),
  selection_method text not null,
  exclusion_checks text[] not null,
  sensor_coverage jsonb not null,
  reference_sources text[] not null,
  quality vigia.reference_quality not null,
  evidence_hash text not null check (length(evidence_hash) = 64),
  created_at timestamptz not null default now(),
  constraint validation_control_period_nonempty check (not isempty(evaluation_period))
);
create index validation_controls_aoi_gist on vigia.validation_control_windows using gist (aoi);
create index validation_controls_period_gist
  on vigia.validation_control_windows using gist (evaluation_period);

create table vigia.validation_engine_versions (
  id uuid primary key default extensions.gen_random_uuid(),
  name text not null unique,
  source_commit text not null,
  fusion_version text not null,
  detection_version text not null,
  risk_version text,
  configuration jsonb not null,
  configuration_hash text not null unique check (length(configuration_hash) = 64),
  automatic_confirmed_fire boolean not null default false check (not automatic_confirmed_fire),
  frozen boolean not null default true check (frozen),
  created_at timestamptz not null default now()
);

alter table vigia.validation_runs
  alter column model_version_id drop not null,
  add column run_key text,
  add column dataset_version_id uuid references vigia.validation_dataset_versions(id),
  add column split_manifest_id uuid references vigia.validation_split_manifests(id),
  add column split_role vigia.validation_split_role,
  add column engine_version_id uuid references vigia.validation_engine_versions(id),
  add column matcher_version text,
  add column matcher_configuration jsonb,
  add column matcher_configuration_hash text check (
    matcher_configuration_hash is null or length(matcher_configuration_hash) = 64
  ),
  add column configuration_hash text check (
    configuration_hash is null or length(configuration_hash) = 64
  ),
  add column sample_counts jsonb not null default '{}'::jsonb,
  add column eligibility_counts jsonb not null default '{}'::jsonb,
  add column excluded_counts jsonb not null default '{}'::jsonb,
  add column limitations text[] not null default '{}',
  add column unavailable_metrics text[] not null default '{}',
  add column report jsonb,
  add column report_hash text check (report_hash is null or length(report_hash) = 64),
  add column published boolean not null default false,
  add column test_access_audit_id uuid,
  add column live_state_mutated boolean not null default false check (not live_state_mutated);

create unique index validation_runs_run_key_unique
  on vigia.validation_runs (run_key) where run_key is not null;
create unique index validation_runs_report_hash_unique
  on vigia.validation_runs (report_hash) where report_hash is not null;
create index validation_runs_dataset_split_idx
  on vigia.validation_runs (dataset_version_id, split_role, started_at desc);

create table vigia.validation_metric_results (
  id bigint generated always as identity primary key,
  validation_run_id uuid not null references vigia.validation_runs(id) on delete cascade,
  metric_name text not null,
  availability vigia.metric_availability not null,
  unit text not null,
  population text not null,
  sample_size integer not null check (sample_size >= 0),
  numerator integer check (numerator is null or numerator >= 0),
  denominator integer check (denominator is null or denominator >= 0),
  metric_value double precision,
  confidence_interval jsonb,
  subgroup jsonb not null default '{}'::jsonb,
  reason text,
  limitations text[] not null default '{}',
  unique (validation_run_id, metric_name, subgroup)
);
create index validation_metric_results_run_idx
  on vigia.validation_metric_results (validation_run_id, metric_name);

create table vigia.validation_matches (
  id uuid primary key default extensions.gen_random_uuid(),
  validation_run_id uuid not null references vigia.validation_runs(id) on delete cascade,
  member_id uuid not null references vigia.validation_dataset_members(id),
  replay_incident_key text not null,
  distance_m double precision not null check (distance_m >= 0),
  absolute_time_gap_seconds double precision not null check (absolute_time_gap_seconds >= 0),
  matcher_version text not null,
  matcher_configuration_hash text not null check (length(matcher_configuration_hash) = 64),
  match_metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (validation_run_id, member_id),
  unique (validation_run_id, replay_incident_key)
);
create index validation_matches_run_idx on vigia.validation_matches (validation_run_id);

create table vigia.validation_errors (
  id uuid primary key default extensions.gen_random_uuid(),
  validation_run_id uuid not null references vigia.validation_runs(id) on delete cascade,
  member_key text,
  replay_incident_key text,
  reason_codes text[] not null,
  evidence jsonb not null,
  manual_override boolean not null default false check (not manual_override),
  created_at timestamptz not null default now()
);
create index validation_errors_run_reason_idx
  on vigia.validation_errors (validation_run_id) include (reason_codes);
create unique index validation_errors_idempotency_idx
  on vigia.validation_errors (
    validation_run_id,
    coalesce(member_key, ''),
    coalesce(replay_incident_key, ''),
    reason_codes
  );

create table vigia.validation_test_access_log (
  id uuid primary key default extensions.gen_random_uuid(),
  access_hash text not null unique check (length(access_hash) = 64),
  split_manifest_id uuid not null references vigia.validation_split_manifests(id),
  engine_version_id uuid not null references vigia.validation_engine_versions(id),
  actor text not null,
  reason text not null,
  requested_at timestamptz not null,
  candidate_configuration_hash text not null check (length(candidate_configuration_hash) = 64),
  candidate_frozen boolean not null check (candidate_frozen),
  commit_sha text not null,
  created_at timestamptz not null default now()
);
create index validation_test_access_split_time_idx
  on vigia.validation_test_access_log (split_manifest_id, requested_at desc);

alter table vigia.validation_runs
  add constraint validation_runs_test_access_fk
  foreign key (test_access_audit_id) references vigia.validation_test_access_log(id);

create or replace function vigia.prevent_frozen_validation_update()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if tg_op = 'DELETE' then
    raise exception 'VALIDATION_IMMUTABLE: no se puede eliminar un artefacto congelado';
  end if;
  if coalesce((to_jsonb(old)->>'frozen')::boolean, false)
     or coalesce((to_jsonb(old)->>'published')::boolean, false) then
    raise exception 'VALIDATION_IMMUTABLE: el artefacto está congelado o publicado';
  end if;
  return new;
end;
$$;

create trigger validation_datasets_immutable
before update or delete on vigia.validation_dataset_versions
for each row execute function vigia.prevent_frozen_validation_update();
create trigger validation_splits_immutable
before update or delete on vigia.validation_split_manifests
for each row execute function vigia.prevent_frozen_validation_update();
create trigger validation_engines_immutable
before update or delete on vigia.validation_engine_versions
for each row execute function vigia.prevent_frozen_validation_update();
create trigger validation_runs_immutable_when_published
before update or delete on vigia.validation_runs
for each row when (old.published)
execute function vigia.prevent_frozen_validation_update();

create or replace function vigia.protect_validation_test_and_audit()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if tg_table_name = 'validation_test_access_log' and tg_op in ('UPDATE', 'DELETE') then
    raise exception 'TEST_AUDIT_IMMUTABLE';
  end if;
  if tg_table_name = 'validation_runs' and new.split_role = 'TEST'
     and new.test_access_audit_id is null then
    raise exception 'TEST_SET_FROZEN: falta auditoría de acceso';
  end if;
  return new;
end;
$$;

create trigger validation_test_access_immutable
before update or delete on vigia.validation_test_access_log
for each row execute function vigia.protect_validation_test_and_audit();
create trigger validation_test_run_requires_audit
before insert or update on vigia.validation_runs
for each row execute function vigia.protect_validation_test_and_audit();

alter table vigia.validation_dataset_versions enable row level security;
alter table vigia.validation_dataset_versions force row level security;
alter table vigia.validation_split_manifests enable row level security;
alter table vigia.validation_split_manifests force row level security;
alter table vigia.validation_dataset_members enable row level security;
alter table vigia.validation_dataset_members force row level security;
alter table vigia.validation_control_windows enable row level security;
alter table vigia.validation_control_windows force row level security;
alter table vigia.validation_engine_versions enable row level security;
alter table vigia.validation_engine_versions force row level security;
alter table vigia.validation_metric_results enable row level security;
alter table vigia.validation_metric_results force row level security;
alter table vigia.validation_matches enable row level security;
alter table vigia.validation_matches force row level security;
alter table vigia.validation_errors enable row level security;
alter table vigia.validation_errors force row level security;
alter table vigia.validation_test_access_log enable row level security;
alter table vigia.validation_test_access_log force row level security;

revoke all on
  vigia.validation_dataset_versions,
  vigia.validation_split_manifests,
  vigia.validation_dataset_members,
  vigia.validation_control_windows,
  vigia.validation_engine_versions,
  vigia.validation_runs,
  vigia.validation_metric_results,
  vigia.validation_matches,
  vigia.validation_errors,
  vigia.validation_test_access_log
from public, anon, authenticated;

revoke all on function vigia.prevent_frozen_validation_update()
from public, anon, authenticated;
revoke all on function vigia.protect_validation_test_and_audit()
from public, anon, authenticated;

commit;
