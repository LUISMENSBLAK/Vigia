# LiDAR PNOA

## Fuente

La fuente es el Centro de Descargas CNIG, serie `LIDA3`. La tesela real seleccionada por catálogo
para la AOI inicial es `PNOA-2025-CYL-356-4502-H30-NPC01.LAZ`; el catálogo publica 5 puntos/m². Su
cabecera declara EPSG:25830, formato de punto 8 y límites 356000–357000 / 4501000–4502000. Cada ejecución
debe conservar edición/cobertura, tesela, URL o id oficial, licencia, ETag cuando exista, tamaño y
SHA-256. Estos valores se validan por producto; no se generalizan a coberturas anteriores.

## Pipeline nacional

```text
catálogo → selección de teselas por AOI → manifiesto → caché/descarga → cabecera LAS/LAZ
→ clasificación disponible → derivados defendibles → COG → metadata/footprint en PostGIS
```

El validador comprueba extensión, legibilidad, número de puntos, formato, versión, bounds, CRS y
checksum. La descarga y el procesamiento son por tesela/AOI e idempotentes. No se descarga España
completa en una sola ejecución.

La descarga oficial observada durante la validación 4B se interrumpió antes de completar el LAZ.
El flujo rechazó el fichero al descomprimir, lo dejó fuera de caché y no publicó DTM, DSM ni canopy.
Por tanto LiDAR permanece `BLOCKED`/`DEGRADADO`, aunque el catálogo y la metadata de la tesela sí
fueron verificables. Reintentar es seguro e idempotente.

## Productos defendibles

Con clasificación y densidad suficientes pueden prepararse DTM, DSM y, tras validación, canopy
height como diferencia compatible DSM−DTM. La calidad debe registrar clases usadas, densidad,
vacíos y resolución. “Vegetation height” o estructura vertical requieren reglas documentadas y una
evaluación específica. LiDAR por sí solo no produce biomasa, humedad ni un modelo de combustible
validado.

Ávila es un demostrador configurado como AOI; el mismo flujo acepta cualquier otra provincia o
polígono sin cambiar el programa. Hasta completar una descarga oficial y registrar sus artefactos,
el estado permanece `BLOCKED`/`UNAVAILABLE`, nunca `AVAILABLE`.
