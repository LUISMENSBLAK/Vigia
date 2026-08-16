# Auditoría LIVE — 2026-08-16

Esta auditoría registra únicamente respuestas observadas. No contiene credenciales, URLs privadas,
coordenadas de hotspots ni datos inventados.

## Supabase / PostGIS

- `SUPABASE_DB_URL`: formato válido, pero DNS/TCP directo y túnel SOCKS no disponibles.
- Data API server-side: HTTP 200 con la secret key.
- Publishable key: HTTP 401; requiere corregirse o regenerarse para el proyecto configurado.
- Schemas `api` y `vigia`: HTTP 406 desde PostgREST; no están expuestos y la migración no pudo
  comprobarse ni aplicarse.
- Migración, PostGIS, RLS, grants y advisors remotos: `NO VERIFICADO`.
- La integración Supabase de la sesión no tiene acceso al proyecto indicado por el `.env`; no se
  tocó ningún proyecto distinto.

La migración local conserva esquemas separados, PostGIS, RLS forzado, grants mínimos, vista
`security_invoker`, índices GiST y constraints. Se añadieron índices para la consulta del último
ingest global y la última procedencia por entidad.

## NASA FIRMS

El Area API respondió correctamente para España, ventana de un día:

| Producto | Observaciones | Confidence | FRP | Brightness | Day/night |
|---|---:|---:|---:|---:|---:|
| VIIRS NOAA-20 NRT | 90 | 90 | 90 | 90 | 90 |
| VIIRS NOAA-21 NRT | 75 | 75 | 75 | 75 | 75 |
| VIIRS SNPP NRT | 79 | 79 | 79 | 79 | 79 |
| MODIS NRT | 4 | 4 | 4 | 4 | 4 |

Total recibido: 248 observaciones térmicas. El parser productivo verificó CSV, timestamps UTC,
plataforma, instrumento y campos científicos. Son observaciones, no incendios.

Persistencia e idempotencia remotas: `NO VERIFICADO`, porque PostgreSQL no fue accesible. No se
guardaron respuestas FIRMS como artefactos locales.

## AEMET

El endpoint oficial de observaciones convencionales devolvió HTTP 502 en la llamada inicial y en
un reintento controlado. No llegó a producirse autenticación ni descarga de datos:
`NO DISPONIBLE`. No se persistió meteorología.

## Copernicus Data Space

- OAuth2 Client Credentials: PASS.
- Duración observada del token: 1800 segundos; el cliente reutilizó el token cacheado.
- Catalog Sentinel-2 L2A sobre una AOI pequeña en Ávila: 5 productos.
- Fechas observadas: `2026-08-08T11:20:06.437Z` a `2026-08-15T11:20:22.892Z`.
- Cloud cover informado por catálogo: 0,36 % a 98,37 %.
- Process API: GeoTIFF 64×64 válido, 50 036 bytes; no se conservó el raster.

No se generaron índices derivados persistentes porque la base no estaba disponible.

## EUMETSAT MTG-FCI

- Cliente OAuth/Data Store implementado contra los endpoints usados por EUMDAC 3.1.1.
- `EUMETSAT_CONSUMER_KEY/EUMETSAT_CONSUMER_SECRET`: autenticación rechazada (HTTP 401).
- Colección `EO:EUM:DAT:0682`: existencia confirmada documentalmente, pero catálogo autenticado
  `NO VERIFICADO`.
- Descarga y lectura netCDF: `NO VERIFICADO`; no se fijaron campos científicos sin abrir un producto
  real.

## API y web

- `/health`: HTTP 200.
- `/v1/status`: HTTP 200 y base `ERROR`, de forma sanitizada.
- `/v1/fire-observations`: GeoJSON válido, cero features y estado `ERROR` mientras la base no está
  disponible.
- `/mapa` conserva clustering visual, selección, procedencia y alternativa textual; sin
  persistencia muestra `SIN OBSERVACIONES ACTIVAS`/`NO DISPONIBLE` y no inventa puntos.

## Bloqueos para estado operativo

No se marca ninguna integración como `OPERATIVO` en producto hasta que la comprobación pueda
persistirse en `vigia.source_health`. Quedan bloqueados PostGIS remoto, RLS/grants reales, advisors,
ingest runs, persistencia FIRMS/AEMET, idempotencia DB, clustering de incidentes y netCDF MTG.

## Verificaciones de código

| Comprobación | Resultado |
|---|---|
| TypeScript | GREEN |
| ESLint | GREEN |
| Vitest | GREEN, 5 tests |
| Next.js build | GREEN, 16 rutas |
| Ruff | GREEN |
| mypy strict | GREEN, 21 módulos |
| pytest | GREEN, 34 tests |
| Playwright | NO EJECUTADO; Chromium no disponible |

La auditoría de accesibilidad en esta ejecución se limita a estructura semántica, foco, estados
textuales y alternativa al mapa. No se declara conformidad WCAG/EN 301 549 sin navegador y pruebas
manuales con tecnología asistiva.
