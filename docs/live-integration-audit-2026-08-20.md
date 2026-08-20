# Auditoría LIVE — 20 de agosto de 2026

Esta evidencia corresponde a una ejecución concreta. No garantiza disponibilidad futura, no valida
precisión científica y no convierte hotspots ni incidentes derivados en incendios confirmados.

## Entorno y secretos

El archivo `.env` local fue convertido desde el adjunto, protegido con permisos locales, comprobado
como ignorado por Git y nunca añadido al índice. Se verificó la presencia de las nueve variables
requeridas sin imprimir valores.

## Supabase / PostGIS

- conexión PostgreSQL remota: verificada;
- PostgreSQL: 17.6;
- PostGIS remoto: 3.3, `USE_GEOS=1`, `USE_PROJ=1`, `USE_STATS=1`;
- migraciones inicial, Fase 3 y Fase 4: aplicadas en orden;
- Fase 4 remota: 4 tablas, 7 índices requeridos y 23 constraints;
- RLS: las 4 tablas de Fase 4 tienen RLS habilitado y forzado;
- `anon` y `authenticated`: sin `SELECT` sobre catálogo ni manifests internos;
- catálogo Fase 4: 2 fuentes añadidas, 0 geometrías administrativas y 0 productos descargados;
- Data API con clave server-side: raíz OpenAPI HTTP 200;
- schemas privados `vigia`/`api`: no expuestos por PostgREST;
- advisors de seguridad/rendimiento de la consola Supabase: `NO VERIFICADO`.

El SQL completo también se ejecutó desde cero en PostgreSQL 17 + PostGIS 3.5 desechable: 34 tablas
internas y las 34 con RLS forzado.

## NASA FIRMS

Consulta nacional real y persistencia idempotente:

| Fuente | Observaciones persistidas |
|---|---:|
| VIIRS NOAA-20 NRT | 114 |
| VIIRS NOAA-21 NRT | 171 |
| VIIRS SNPP NRT | 98 |
| MODIS NRT | 8 |
| Total | 391 |

Las 391 filas conservaron tiempo, coordenadas dentro del bbox consultado, FRP, confidence raw,
plataforma, sensor, día/noche y provenance. Rango observado: 2026-08-20 00:43–04:34 UTC.

## Fusión sobre datos reales

`as_of=2026-08-20T07:00:00Z`: 391 observaciones recibidas, 389 elegibles, 43 clusters y 31
incidentes persistidos. Estados: 29 `VIGILANCIA`, 2 `PROBABLE_INCENDIO`, 0
`INCENDIO_CONFIRMADO`. Familias presentes: NASA VIIRS y NASA MODIS. El resultado comprueba la
integración, no calibra probabilidad ni confirma incendios.

## AEMET OpenData

El endpoint de datos devolvió JSON real en ISO-8859-1 aunque declaró `text/plain`; el adaptador se
actualizó para aceptar esa codificación oficial sin relajar la validación estructural. Se
persistieron 9.606 observaciones de 846 estaciones, todas `OBSERVADO`, entre 2026-08-19 19:00 y
2026-08-20 06:00 UTC. Disponibilidad por campo: temperatura 9.527, humedad 9.523, viento 8.471,
racha 8.447, precipitación 9.327 y presión 3.503. No se fabricaron interpolaciones ni pronósticos.

## Copernicus

- OAuth real: verificado y token reutilizado desde caché;
- catálogo nacional Sentinel-2 L2A: 5 productos devueltos en la consulta nacional inicial;
- catálogo para AOI pequeña de Ávila: 5 productos entre el 13 y el 18 de agosto;
- Process API: GeoTIFF 64×64, 4 bandas, EPSG:4326, 49.599 bytes;
- máscara SCL/dataMask: 4.096/4.096 píxeles válidos; índices finitos NDVI/NDMI/NBR:
  4.089/4.087/4.087;
- SHA-256 del resultado: `6d244f382a5190ec6b6a1396e3672eae97a261129444330b370e060c8f864a42`.

La muestra EPSG:4326 es una validación técnica de Process API. No se registró como COG métrico ni
como capa `AVAILABLE`, porque la base Fase 4 exige resolución en metros y provenance de producto
inequívoco.

## EUMETSAT

OAuth respondió con rechazo de autenticación. Catálogo, acceso a `EO:EUM:DAT:0682`, producto real y
lectura netCDF: `NO VERIFICADO`. No se descargó ningún volumen.

## Fuentes geoespaciales oficiales

- WFS de unidades administrativas IGN: GetCapabilities HTTP 200 y GetFeature GML legible;
- catálogo CNIG LiDAR 3.ª cobertura: accesible y con publicación de Castilla y León documentada;
- LiDAR/MDT de Ávila: no descargado ni procesado, por lo que continúa `UNAVAILABLE`;
- CORINE: fuente registrada, producto no descargado.

No se insertaron límites administrativos ni productos de prueba en el remoto. Los endpoints de
capas, cobertura (bbox, GeoJSON y área administrativa) y contexto respondieron HTTP 200 con cero
productos y `NO DISPONIBLE`, que es el estado verificable actual.
