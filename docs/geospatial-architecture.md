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

El contexto actual devuelve metadatos y `NO DISPONIBLE` para valores de píxel hasta que se publique
un lector de COG seguro. Esto evita aparentar datos que el catálogo todavía no puede servir.

## Escalado

El procesamiento es incremental, por AOI y tesela, cacheable mediante product id, ETag y SHA-256,
y paralelizable sin requerir infraestructura distribuida. España completa se construye como suma
de productos verificables; no como una ejecución monolítica.
