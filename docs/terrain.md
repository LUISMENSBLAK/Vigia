# Terreno

## Fuentes y productos

La fuente prioritaria es CNIG/IGN-PNOA. El Centro de Descargas publica MDT y MDS oficiales en varias
resoluciones; la resolución concreta se lee del producto y nunca se presupone. Para cada AOI se
conserva el raster de elevación aceptado y se pueden derivar:

- pendiente, en grados;
- orientación, en grados azimutales;
- ruggedness, como diferencia media absoluta respecto de vecinos;
- elevación original, en las unidades declaradas por el producto.

La fórmula y versión de cada derivado se guardan como `algorithm` y `software_version`. No se
calculan métricas sobre EPSG:4326: el raster debe utilizar un CRS proyectado en metros.

## Validación raster y COG

Antes de aceptar un producto se comprueban fichero no vacío, driver, dimensiones, número de bandas,
CRS, geotransformación, bounds, resolución, nodata y SHA-256. Los COG se generan con teselas,
compresión sin pérdida y overviews; se vuelven a abrir y validar. Un fichero corrupto nunca pasa a
`AVAILABLE`.

Nodata se propaga a pendiente, orientación y ruggedness. No se rellenan huecos de elevación sin un
algoritmo de interpolación declarado y evaluado.

## Resolución

No se fusionan silenciosamente MDT de 2 m, 5 m o 25 m. Cada producto conserva
`source_resolution_m`, `output_resolution_m` y `resampling_algorithm`. Las estadísticas zonales
futuras podrán usar `terrain_cells` como índice/agregado; esas celdas no reemplazan los píxeles.
