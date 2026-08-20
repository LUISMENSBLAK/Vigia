# Procedencia y lineage

Toda entidad derivada debe responder: dataset, versión, timestamp, transformación, modelo, commit,
parámetros e inputs. `vigia.data_provenance` almacena esa cadena mediante hashes de entrada y salida.

Un producto satelital conserva sensing/availability/receipt timestamps, footprint, CRS, resolución,
calidad, URI y SHA-256. Una observación enlaza producto, fuente e ingest run. Una predicción enlaza
model version y provenance. Una ejecución de validación conserva dataset hash y configuración.

Los archivos raster o LiDAR no se almacenan como blobs en PostgreSQL. Se mantienen como artefactos
versionados (preferiblemente COG), mientras la base conserva metadata, bbox, resolución, URI,
checksum y procedencia.

La ingestión FIRMS calcula un identificador estable a partir de fuente, coordenadas, tiempo,
plataforma e instrumento. El payload original se conserva en `raw_properties`; un hash del input y
otro de la fila normalizada se escriben solo cuando la observación se inserta por primera vez. Una
repetición idempotente registra su propio `ingest_run`, pero no duplica observación ni provenance.

AEMET aplica el mismo patrón con estación y timestamp. `OBSERVADO` es un valor explícito del modelo;
los futuros datos `INTERPOLADO` y `PRONOSTICADO` deberán recorrer contratos separados.

Cada ejecución de fusión conserva `as_of`, rango observado, configuración canónica y hash, versión,
commit, familias, conteos y candidatos. Las asociaciones son idempotentes. Cada transición de
incidente conserva estado anterior/nuevo, reason codes, snapshot de observaciones, run, regla,
software, commit y configuration hash; el historial no se sobrescribe.

Fase 4 añade un catálogo raster/LiDAR que conserva proveedor, dataset, product id, ficheros o ids de
entrada, hashes de entrada, versión de procesamiento, configuration hash, software, timestamps,
CRS de entrada/salida, resolución de entrada/salida, remuestreo, algoritmo, footprint, calidad,
storage URI y output hash. `download_manifests` registra solicitud, finalización, tamaño, checksum,
ETag, estado y hash de AOI, pero nunca tokens.

`AVAILABLE` requiere un artefacto local/objeto y hash verificables. Un registro de catálogo o una
respuesta HTTP correcta no basta para declarar una capa disponible. El `as_of` de API y Replay
filtra tanto adquisición como procesamiento para impedir future leakage.
