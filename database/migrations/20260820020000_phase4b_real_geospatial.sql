begin;

-- Service reachability and product freshness are intentionally independent.
-- Existing `state`/`checked_at` remain the service check contract used by workers.
alter table vigia.source_health
  add column if not exists last_success_at timestamptz,
  add column if not exists last_product_at timestamptz,
  add column if not exists last_ingest_at timestamptz,
  add column if not exists check_interval_seconds integer,
  add column if not exists product_freshness_seconds integer;

alter table vigia.source_health
  add constraint source_health_check_interval_positive
    check (check_interval_seconds is null or check_interval_seconds > 0),
  add constraint source_health_product_freshness_positive
    check (product_freshness_seconds is null or product_freshness_seconds > 0);

update vigia.source_health health
set
  last_success_at = coalesce(health.last_success_at, health.checked_at)
where health.state = 'OPERATIVO';

update vigia.source_health health
set
  last_product_at = coalesce(health.last_product_at, health.last_observed_at),
  last_ingest_at = coalesce(health.last_ingest_at, health.last_received_at),
  check_interval_seconds = coalesce(
    health.check_interval_seconds,
    case
      when source.code like 'NASA_FIRMS_%' then 21600
      when source.code = 'AEMET_OPEN_DATA' then 10800
      when source.code like 'COPERNICUS_SENTINEL_%' then 604800
      when source.code = 'EUMETSAT_MTG_FCI_AFM' then 1800
      else 86400
    end
  ),
  product_freshness_seconds = coalesce(
    health.product_freshness_seconds,
    case
      when source.code like 'NASA_FIRMS_%' then 43200
      when source.code = 'AEMET_OPEN_DATA' then 21600
      when source.code like 'COPERNICUS_SENTINEL_%' then 1209600
      when source.code = 'EUMETSAT_MTG_FCI_AFM' then 3600
      else 2592000
    end
  )
from vigia.sources source
where source.id = health.source_id;

drop view api.source_health;
create view api.source_health
with (security_invoker = true)
as
select
  s.code,
  s.name,
  h.state as service_state,
  h.checked_at,
  h.last_success_at,
  h.last_product_at,
  h.last_ingest_at,
  h.last_observed_at,
  h.last_received_at,
  h.latency_seconds,
  h.check_interval_seconds,
  h.product_freshness_seconds,
  case
    when h.last_product_at is null then 'NO_DATA'
    when h.product_freshness_seconds is null then 'UNKNOWN'
    when h.last_product_at + make_interval(secs => h.product_freshness_seconds) >= now()
      then 'CURRENT'
    else 'STALE'
  end as data_freshness,
  (
    h.check_interval_seconds is not null
    and h.checked_at + make_interval(secs => h.check_interval_seconds) < now()
  ) as service_check_overdue,
  h.error_code,
  h.detail
from vigia.source_health h
join vigia.sources s on s.id = h.source_id
where h.is_public = true;

revoke all on api.source_health from public;
grant select on api.source_health to anon, authenticated;

insert into vigia.sources (code, name, provider, dataset_version, license_uri, metadata)
values
  (
    'IGN_MDT05', 'Modelo Digital del Terreno MDT05',
    'Instituto Geográfico Nacional / CNIG', 'MDT05',
    'https://www.ign.es/resources/licencia/Condiciones_licenciaUso_IGN.pdf',
    '{"dataset":"MDT05","resolution_m":5,"service":"WCS","scope":"national"}'::jsonb
  ),
  (
    'IGN_SIOSE_AR_2017', 'SIOSE AR 2017',
    'Instituto Geográfico Nacional / IDEE', 'siose_ar2017',
    'https://www.ign.es/resources/licencia/Condiciones_licenciaUso_IGN.pdf',
    '{"dataset":"Sistema de Información de Ocupación del Suelo en España 2017","service":"WFS","not_a_fuel_model":true}'::jsonb
  ),
  (
    'EUROSTAT_GISCO_COUNTRIES', 'Países GISCO',
    'Eurostat GISCO', '2024-10M',
    'https://ec.europa.eu/eurostat/web/gisco/geodata/administrative-units/countries',
    '{"dataset":"Countries 2024","generalisation":"10M","scope":"europe"}'::jsonb
  )
on conflict (code) do update set
  dataset_version = excluded.dataset_version,
  metadata = vigia.sources.metadata || excluded.metadata;

alter table vigia.geospatial_products
  alter column source_resolution_m drop not null,
  alter column output_resolution_m drop not null,
  add column if not exists raster_band integer,
  add column if not exists value_units text,
  add column if not exists published_at timestamptz,
  add column if not exists invalidated_at timestamptz,
  add column if not exists superseded_by uuid references vigia.geospatial_products(id),
  add column if not exists render_hint jsonb not null default '{}'::jsonb;

alter table vigia.geospatial_products
  add constraint geospatial_raster_band_positive
    check (raster_band is null or raster_band > 0),
  add constraint geospatial_publication_order
    check (published_at is null or processed_at is null or published_at >= processed_at),
  add constraint geospatial_invalidation_order
    check (invalidated_at is null or published_at is null or invalidated_at >= published_at);

create index geospatial_products_current_idx
  on vigia.geospatial_products (layer, observed_at desc)
  where invalidated_at is null;

create table vigia.land_cover_features (
  id uuid primary key default extensions.gen_random_uuid(),
  product_id uuid not null references vigia.geospatial_products(id) on delete cascade,
  external_id text not null,
  class_uri text not null,
  class_code text not null,
  covered_percentage double precision,
  observed_at timestamptz,
  geometry extensions.geometry(MultiPolygon, 4326) not null,
  properties jsonb not null default '{}'::jsonb,
  unique (product_id, external_id),
  constraint land_cover_percentage_range check (
    covered_percentage is null or covered_percentage between 0 and 100
  )
);
create index land_cover_features_geometry_gist
  on vigia.land_cover_features using gist (geometry);
create index land_cover_features_product_idx
  on vigia.land_cover_features (product_id, class_code);

alter table vigia.land_cover_features enable row level security;
alter table vigia.land_cover_features force row level security;
revoke all on vigia.land_cover_features from public, anon, authenticated;

commit;
