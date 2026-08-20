begin;

create type vigia.risk_mode as enum ('ANALYSIS', 'FORECAST');
create type vigia.risk_data_quality as enum ('COMPLETE', 'PARTIAL', 'INSUFFICIENT_DATA');

create table vigia.risk_runs (
  id uuid primary key default extensions.gen_random_uuid(),
  engine_version text not null,
  mode vigia.risk_mode not null,
  state vigia.ingest_state not null,
  as_of timestamptz not null,
  valid_at timestamptz not null,
  horizon_hours integer not null check (horizon_hours between 0 and 240),
  aoi extensions.geometry(MultiPolygon, 4326) not null,
  aoi_hash text not null,
  configuration jsonb not null,
  configuration_hash text not null,
  input_snapshot jsonb not null,
  input_snapshot_hash text not null,
  software_version text not null,
  code_commit text not null,
  request_id text not null,
  started_at timestamptz not null,
  finished_at timestamptz,
  data_quality vigia.risk_data_quality,
  errors jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  constraint risk_run_time_order check (finished_at is null or finished_at >= started_at),
  constraint risk_run_temporal_contract check (
    (mode = 'ANALYSIS' and horizon_hours = 0 and valid_at = as_of)
    or (mode = 'FORECAST' and valid_at >= as_of)
  ),
  unique (engine_version, mode, as_of, valid_at, aoi_hash, configuration_hash, input_snapshot_hash)
);
create index risk_runs_aoi_gist on vigia.risk_runs using gist (aoi);
create index risk_runs_time_idx on vigia.risk_runs (as_of desc, valid_at desc);
create index risk_runs_state_idx on vigia.risk_runs (state, started_at desc);

alter table vigia.risk_predictions
  alter column model_version_id drop not null,
  alter column risk_score drop not null,
  alter column level drop not null,
  alter column top_factors drop not null,
  alter column data_quality drop not null,
  add column run_id uuid references vigia.risk_runs(id) on delete cascade,
  add column prediction_key text,
  add column mode vigia.risk_mode,
  add column as_of timestamptz,
  add column horizon_hours integer,
  add column centroid extensions.geography(Point, 4326),
  add column experimental_index double precision,
  add column risk_class text,
  add column component_scores jsonb not null default '{}'::jsonb,
  add column component_details jsonb not null default '{}'::jsonb,
  add column reason_codes text[] not null default '{}',
  add column explanations text[] not null default '{}',
  add column missing_components text[] not null default '{}',
  add column input_resolutions jsonb not null default '{}'::jsonb,
  add column engine_version text,
  add column configuration_hash text,
  add column input_snapshot_hash text,
  add column output_hash text,
  add column raster_product_id uuid references vigia.geospatial_products(id),
  add column experimental boolean not null default true;

alter table vigia.risk_predictions
  add constraint risk_prediction_index_range check (
    experimental_index is null or experimental_index between 0 and 100
  ),
  add constraint risk_prediction_horizon_range check (
    horizon_hours is null or horizon_hours between 0 and 240
  ),
  add constraint risk_prediction_phase5_complete check (
    run_id is null or (
      prediction_key is not null and mode is not null and as_of is not null
      and horizon_hours is not null and risk_class is not null
      and engine_version is not null and configuration_hash is not null
      and input_snapshot_hash is not null and output_hash is not null
    )
  );
create unique index risk_predictions_prediction_key_idx
  on vigia.risk_predictions (prediction_key) where prediction_key is not null;
create index risk_predictions_centroid_gist
  on vigia.risk_predictions using gist (centroid) where centroid is not null;
create index risk_predictions_mode_time_idx
  on vigia.risk_predictions (mode, as_of desc, valid_at desc) where run_id is not null;

alter table vigia.geospatial_products
  drop constraint geospatial_products_layer_check;
alter table vigia.geospatial_products
  add constraint geospatial_products_layer_check check (layer in (
    'ELEVATION', 'SLOPE', 'ASPECT', 'TERRAIN_RUGGEDNESS',
    'NDVI', 'NDMI', 'NBR', 'LAND_COVER', 'LIDAR_DTM', 'LIDAR_DSM',
    'CANOPY_HEIGHT', 'FUEL_PROXY', 'RISK_BASELINE', 'FWI', 'RISK_DATA_QUALITY'
  ));

alter table vigia.risk_runs enable row level security;
alter table vigia.risk_runs force row level security;
alter table vigia.risk_predictions force row level security;

revoke all on vigia.risk_runs from public, anon, authenticated;
revoke all on vigia.risk_predictions from public, anon, authenticated;

commit;
