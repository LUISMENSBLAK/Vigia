# Arquitectura geoespacial nacional

## Alcance

La unidad de procesamiento es una `AOI`, nunca una provincia codificada en el programa. Una AOI
puede proceder de bbox, Polygon/MultiPolygon GeoJSON, una unidad administrativa oficial almacenada
en PostGIS o el contorno nacional. Ávila es solo la primera AOI de validación de alta resolución.
Cambiar de provincia modifica configuración y datos, no código.

## Flujo

```text
catálogo oficial → selección por AOI/as_of → manifiesto → descarga validada → artefacto raw
→ transformación por teselas → COG → almacenamiento → footprint/metadata/provenance en PostGIS
→ API de contexto/cobertura → mapa
```

Los raster y las nubes LiDAR viven en almacenamiento de ficheros mediante una interfaz sustituible
por object storage. PostgreSQL conserva AOIs, jerarquía administrativa, footprints, estados,
resoluciones, fechas, índices, hashes y procedencia. No se almacenan píxeles nacionales como
millones de polígonos ni como blobs indiscriminados.

## AOI y límites

`vigia_geospatial.aoi.AOIRequest` obliga a elegir exactamente un selector. La geometría se valida
en EPSG:4326, se calcula su superficie geodésicamente y se rechazan peticiones que exceden el límite
configurado. Las unidades administrativas deben venir del conjunto oficial IGN/CNIG y mantener
España → comunidad autónoma → provincia → municipio. La migración crea la estructura, pero no
inventa ni precarga límites.

## CRS

Footprints y contrato web usan EPSG:4326. Distancias, áreas y derivados métricos requieren un CRS
proyectado en metros. Para Península y Baleares se selecciona ETRS89/UTM 29N, 30N o 31N según la AOI;
Canarias y productos fuera de ese ámbito conservan el CRS oficial adecuado y exigen configuración
explícita. Cada producto registra CRS de entrada y salida. El remuestreo registra resolución de
origen, resolución final y algoritmo.

## Catálogo y disponibilidad

`vigia.geospatial_products` mantiene `AVAILABLE`, `PARTIAL`, `STALE`, `UNAVAILABLE`, `PROCESSING` o
`ERROR`. `AVAILABLE` exige URI de almacenamiento y hash de salida. La ausencia de un producto no se
convierte en un valor estimado. `fuel_proxy`, cuando exista, queda forzado a `EXPERIMENTAL` y nunca
equivale a un modelo de combustible validado.

Los endpoints son:

- `GET /api/geospatial/layers`: estado agregado por capa.
- `GET /api/geospatial/coverage`: footprints que intersectan un bbox y existían en `as_of`.
- `GET /api/geospatial/context`: productos que cubren un punto en `as_of`.
- `GET /api/geospatial/tiles/{product_id}/{z}/{x}/{y}.png`: teselas PNG generadas desde el COG
  materializado, sin exponer rutas locales.

El contexto muestrea los COG locales cuando el nodo posee el artefacto y devuelve clases SIOSE
vectoriales donde existe cobertura. Si el nodo no comparte el almacenamiento, el valor permanece
`NO DISPONIBLE`; la metadata no se convierte en un valor inventado. El mapa consume los mismos
footprints y endpoints y diferencia la capa científica de la capa «Cobertura de datos».

## Materializador 4B

`scripts/materialize_phase4b.py` recibe un JSON de AOI proyectada. La configuración inicial cubre
una tesela de 1 km² dentro de Ávila y contiene también una provincia adicional para demostrar que
la jerarquía cambia por datos, no por funciones `process_avila`. El flujo es incremental e
idempotente: un nuevo producto vigente invalida el anterior de la misma capa/AOI mediante
`invalidated_at` y `superseded_by`; no lo borra.

La consulta puntual resuelve también todas las unidades administrativas oficiales que cubren la
coordenada y devuelve su id, nivel, dataset, vigencia, fuente y provenance. Cada valor raster incluye
`data_age_seconds`, fecha, resolución, calidad y producto; la antigüedad no altera por sí misma el
estado del servicio que lo suministró.

El backend actual de storage es `LocalStorage`, confinado a `GEOSPATIAL_STORAGE_ROOT`. Su contrato
permite sustituirlo por object storage. Las URI firmadas de proveedores nunca se guardan en
manifiestos ni provenance.

## Escalado

El procesamiento es incremental, por AOI y tesela, cacheable mediante product id, ETag y SHA-256,
y paralelizable sin requerir infraestructura distribuida. España completa se construye como suma
de productos verificables; no como una ejecución monolítica.

## Superficies de riesgo

Fase 5 reutiliza RAW/COG/storage/PostGIS. Los grids deben estar alineados explícitamente;
el motor rechaza mezclas silenciosas de CRS o resolución. La calidad se materializa como
una capa distinta. Los territorios no peninsulares usan CRS métricos regionales.
