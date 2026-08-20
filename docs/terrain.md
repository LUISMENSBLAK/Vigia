# Terreno

## Fuentes y productos

La primera fuente materializable es el WCS oficial MDT del IGN/IDEE
`https://servicios.idee.es/wcs-inspire/mdt`. La cobertura `Elevacion25830_5` declara ETRS89 / UTM
30N y paso de 5 m. El pipeline solicita únicamente el recorte de la AOI, conserva el GeoTIFF raw y
deriva:

- pendiente, en grados;
- orientación, en grados azimutales;
- ruggedness, como terrain ruggedness index de vecinos;
- elevación original, en las unidades declaradas por el producto.

La fórmula y versión de cada derivado se guardan como `algorithm` y `software_version`. No se
calculan métricas sobre EPSG:4326: el raster debe utilizar un CRS proyectado en metros.

La AOI inicial mide 1×1 km en EPSG:25830. No representa cobertura nacional: el catálogo y el mapa
publican su footprint exacto. Ampliar España exige iterar AOIs/teselas, nunca inferir cobertura a
partir de esa muestra.

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
