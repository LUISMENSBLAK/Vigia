# LiDAR PNOA

## Fuente

La fuente prioritaria es el Centro de Descargas CNIG. La tercera cobertura PNOA (2022–2025) se
distribuye en teselas LAZ de 1×1 km con densidad nominal publicada de 5 puntos/m². Cada ejecución
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

## Productos defendibles

Con clasificación y densidad suficientes pueden prepararse DTM, DSM y, tras validación, canopy
height como diferencia compatible DSM−DTM. La calidad debe registrar clases usadas, densidad,
vacíos y resolución. “Vegetation height” o estructura vertical requieren reglas documentadas y una
evaluación específica. LiDAR por sí solo no produce biomasa, humedad ni un modelo de combustible
validado.

Ávila será un demostrador configurado como AOI; el mismo flujo debe aceptar cualquier otra provincia
o polígono sin cambiar el programa. Hasta completar una descarga oficial y registrar sus artefactos,
el estado permanece `UNAVAILABLE` o `PROCESSING`, nunca `AVAILABLE`.
