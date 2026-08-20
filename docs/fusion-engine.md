# Fusion Engine — baseline research

Estado: `EXPERIMENTAL`. No produce una probabilidad operacional ni confirma incendios.

## Entrada común

`ObservationEvidence` conserva identificador, fuente, proveedor, plataforma, sensor, tiempos
observado/recibido/procesado, coordenadas, resolución, edad, confidence original, probabilidad solo
si el producto realmente la proporciona, FRP, brillo, día/noche, calidad, provenance y familia.
La normalización nunca traduce el confidence textual FIRMS a probabilidad.

## Familias e independencia

- `NASA_VIIRS`: NOAA-20, NOAA-21 y SNPP; son plataformas distintas de una familia correlacionada.
- `NASA_MODIS`.
- `EUMETSAT_MTG`.
- `COPERNICUS_OPTICAL`, `COPERNICUS_RADAR` y `COPERNICUS_THERMAL`.
- `AEMET_WEATHER`, `TERRAIN`, `VEGETATION` y `UNKNOWN`.

Contar plataformas no equivale a contar evidencias independientes. El detector exige al menos dos
familias térmicas para recomendar `PROBABLE_INCENDIO`.

## Clustering

El baseline ordena por tiempo, usa buckets espaciales y una ventana móvil, y valida cada asociación
con distancia great-circle en metros. La consulta productiva usa `geography` y `ST_DWithin` para
fuentes térmicas conocidas. Los radios, resoluciones, ventanas y expiración viven en
`config/fusion.v1.json`; su JSON canónico genera el `configuration_hash`.

Primero se agrupan observaciones térmicas. Meteorología y otros contextos solo se adjuntan después y
no pueden unir dos clusters térmicos. La salida conserva centroid, extensión, plataformas, sensores,
familias, roles `confirming/contradicting/context` y métricas de persistencia.

## Determinismo y replay

Con los mismos inputs, `as_of`, configuración y versión, la salida es idéntica. Ninguna observación
observada, recibida o procesada después de `as_of` entra en la ejecución. El CLI acepta `--from`,
`--to` y `--as-of`, por lo
que la misma lógica sirve para LIVE y replay histórico. Los fixtures sintéticos viven únicamente
en `tests/fixtures`.

## Persistencia

`fusion_runs` registra rango, fuentes, configuración, commit y conteos. `incident_candidates`
conserva toda agrupación; un `fire_incident` solo nace al alcanzar el mínimo conservador de
observaciones. La clave del incidente deriva de la primera señal confirmatoria y el upsert evita
duplicados cuando llegan evidencias posteriores.
`known_heat_sources` y `controlled_burn_context` están vacías hasta disponer de fuentes oficiales.

## Limitaciones

Los parámetros son hipótesis iniciales sin calibración. No se midieron precision, recall, latencia
operacional ni correlación empírica. La ausencia de detección de un sensor no se interpreta aún como
contradicción salvo que exista un registro explícito y científicamente compatible.
