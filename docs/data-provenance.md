# Procedencia y lineage

Toda entidad derivada debe responder: dataset, versión, timestamp, transformación, modelo, commit,
parámetros e inputs. `vigia.data_provenance` almacena esa cadena mediante hashes de entrada y salida.

Un producto satelital conserva sensing/availability/receipt timestamps, footprint, CRS, resolución,
calidad, URI y SHA-256. Una observación enlaza producto, fuente e ingest run. Una predicción enlaza
model version y provenance. Una ejecución de validación conserva dataset hash y configuración.

Los archivos raster o LiDAR no se almacenan como blobs en PostgreSQL. Se mantienen como artefactos
versionados (preferiblemente COG), mientras la base conserva metadata, bbox, resolución, URI,
checksum y procedencia.
