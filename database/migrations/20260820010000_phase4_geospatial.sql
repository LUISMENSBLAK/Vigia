begin;

create type vigia.geospatial_availability as enum (
  'AVAILABLE', 'PARTIAL', 'STALE', 'UNAVAILABLE', 'PROCESSING', 'ERROR'
);
create type vigia.administrative_level as enum (
  'COUNTRY', 'AUTONOMOUS_COMMUNITY', 'PROVINCE', 'MUNICIPALITY'
);

insert into vigia.sources (code, name, provider, dataset_version, license_uri, metadata)
values
  (
    'IGN_ADMINISTRATIVE_UNITS', 'Unidades administrativas de España',
    'Instituto Geográfico Nacional / CNIG', null,
    'https://www.ign.es/resources/licencia/Condiciones_licenciaUso_IGN.pdf',
    '{"dataset":"BD de Divisiones Administrativas de España","scope":"national"}'::jsonb
  ),
  (
    'COPERNICUS_CORINE_LAND_COVER', 'CORINE Land Cover',
    'Copernicus Land Monitoring Service', '2018-v2020_20u1',
    'https://land.copernicus.eu/en/data-policy',
    '{"dataset":"CORINE Land Cover","resolution_m":100,"not_a_fuel_model":true}'::jsonb
  )
on conflict (code) do nothing;

create table vigia.administrative_areas (
  id uuid primary key default extensions.gen_random_uuid(),
  source_id uuid not null references vigia.sources(id),
  external_id text not null,
  name text not null,
  level vigia.administrative_level not null,
  parent_id uuid references vigia.administrative_areas(id),
  geometry extensions.geometry(MultiPolygon, 4326) not null,
  valid_from timestamptz,
  valid_to timestamptz,
  dataset_version text not null,
  provenance_id uuid references vigia.data_provenance(id),
  created_at timestamptz not null default now(),
  unique (source_id, external_id, dataset_version),
  constraint administrative_area_validity check (
    valid_to is null or valid_from is null or valid_to >= valid_from
  )
);
create index administrative_areas_geometry_gist
  on vigia.administrative_areas using gist (geometry);
create index administrative_areas_parent_idx on vigia.administrative_areas (parent_id);
create index administrative_areas_level_name_idx on vigia.administrative_areas (level, name);

create table vigia.geospatial_products (
  id uuid primary key default extensions.gen_random_uuid(),
  source_id uuid not null references vigia.sources(id),
  product_id text not null,
  layer text not null check (layer in (
    'ELEVATION', 'SLOPE', 'ASPECT', 'TERRAIN_RUGGEDNESS',
    'NDVI', 'NDMI', 'NBR', 'LAND_COVER', 'LIDAR_DTM', 'LIDAR_DSM',
    'CANOPY_HEIGHT', 'FUEL_PROXY'
  )),
  availability vigia.geospatial_availability not null,
  observed_at timestamptz,
  processed_at timestamptz,
  footprint extensions.geometry(MultiPolygon, 4326) not null,
  source_uri text,
  storage_uri text,
  source_crs text not null,
  output_crs text not null,
  source_resolution_m double precision not null check (source_resolution_m > 0),
  output_resolution_m double precision not null check (output_resolution_m > 0),
  resampling_algorithm text,
  nodata double precision,
  raster_metadata jsonb not null default '{}'::jsonb,
  quality jsonb not null default '{}'::jsonb,
  input_hashes text[] not null default '{}',
  output_hash text,
  configuration_hash text not null,
  software_version text not null,
  algorithm text not null,
  is_experimental boolean not null default false,
  provenance_id uuid references vigia.data_provenance(id),
  created_at timestamptz not null default now(),
  unique (source_id, product_id, layer, configuration_hash),
  constraint geospatial_product_time_order check (
    processed_at is null or observed_at is null or processed_at >= observed_at
  ),
  constraint fuel_proxy_is_experimental check (
    layer <> 'FUEL_PROXY' or is_experimental = true
  ),
  constraint available_product_has_output check (
    availability <> 'AVAILABLE' or (storage_uri is not null and output_hash is not null)
  )
);
create index geospatial_products_footprint_gist
  on vigia.geospatial_products using gist (footprint);
create index geospatial_products_layer_time_idx
  on vigia.geospatial_products (layer, observed_at desc);
create index geospatial_products_availability_idx
  on vigia.geospatial_products (availability, layer);

create table vigia.download_manifests (
  id uuid primary key default extensions.gen_random_uuid(),
  source_id uuid not null references vigia.sources(id),
  product_id text not null,
  source_uri text not null,
  requested_at timestamptz not null,
  downloaded_at timestamptz,
  size_bytes bigint check (size_bytes is null or size_bytes >= 0),
  checksum_sha256 text,
  etag text,
  status vigia.geospatial_availability not null,
  aoi_hash text not null,
  error_code text,
  request_id text not null,
  created_at timestamptz not null default now(),
  unique (source_id, product_id, aoi_hash),
  constraint manifest_download_time check (
    downloaded_at is null or downloaded_at >= requested_at
  )
);
create index download_manifests_status_idx on vigia.download_manifests (status, requested_at desc);

create table vigia.geospatial_processing_runs (
  id uuid primary key default extensions.gen_random_uuid(),
  state vigia.ingest_state not null,
  layer text not null,
  aoi extensions.geometry(MultiPolygon, 4326) not null,
  as_of timestamptz not null,
  started_at timestamptz not null,
  finished_at timestamptz,
  configuration jsonb not null,
  configuration_hash text not null,
  software_version text not null,
  code_commit text not null,
  request_id text not null,
  errors jsonb not null default '[]'::jsonb,
  constraint geospatial_run_time_order check (
    finished_at is null or finished_at >= started_at
  )
);
create index geospatial_processing_runs_aoi_gist
  on vigia.geospatial_processing_runs using gist (aoi);
create index geospatial_processing_runs_as_of_idx
  on vigia.geospatial_processing_runs (as_of desc);

alter table vigia.administrative_areas enable row level security;
alter table vigia.administrative_areas force row level security;
alter table vigia.geospatial_products enable row level security;
alter table vigia.geospatial_products force row level security;
alter table vigia.download_manifests enable row level security;
alter table vigia.download_manifests force row level security;
alter table vigia.geospatial_processing_runs enable row level security;
alter table vigia.geospatial_processing_runs force row level security;

revoke all on table
  vigia.administrative_areas,
  vigia.geospatial_products,
  vigia.download_manifests,
  vigia.geospatial_processing_runs
from public, anon, authenticated;

commit;
