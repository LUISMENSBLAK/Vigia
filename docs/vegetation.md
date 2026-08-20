# Vegetación

## Índices Sentinel-2

La base implementa NDVI `(B08-B04)/(B08+B04)`, NDMI `(B08-B11)/(B08+B11)` y NBR
`(B08-B12)/(B08+B12)`. Se conservan el identificador del producto L2A, adquisición, bandas,
resolución, cloud cover de catálogo, AOI, CRS, fecha de procesamiento y hashes. Un índice es una
observación temporal de la superficie, no una propiedad permanente.

## Máscaras y calidad

Los píxeles SCL 0, 1, 3, 8, 9, 10 y 11 —sin datos, defectuosos, sombra de nube, nubes y nieve— y
los píxeles con `dataMask=0` se convierten en nodata antes de calcular índices. El filtro de cloud
cover del catálogo reduce candidatos, pero no sustituye el enmascarado por píxel. La calidad debe
registrar porcentaje válido y método de máscara.

## Tiempo y Replay

Cada valor conserva `observed_at`, `processed_at`, product id y resolución. Una consulta con
`as_of=T` excluye productos observados o procesados después de T. Las pruebas automatizadas cubren
esta barrera para evitar data leakage durante Replay.

## Cobertura y fuel proxy

Vegetación disponible, cobertura del suelo y modelo de combustible son conceptos distintos. CORINE
puede aportar `LAND_COVER`; no se presenta como combustible. Una combinación futura de cobertura,
altura, continuidad e índices solo podrá llamarse `FUEL_PROXY`, deberá ser `EXPERIMENTAL` y mostrar
sus faltantes y fecha. No se infieren biomasa ni humedad sin datos y validación adecuados.
