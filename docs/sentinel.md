# Sentinel

## Sentinel-2

El cliente usa OAuth2 cacheado de Copernicus Data Space, Catalog STAC por bbox/fecha y Process API
para AOIs acotadas. Prioriza L2A y registra product id, adquisición, footprint, cloud cover y
metadata. Las peticiones de índices incluyen B04, B08, B11, B12, SCL y `dataMask`; el mosaico usa
la fecha más reciente y limita cloud cover de catálogo, sin confundir ese umbral con ausencia de
nubes a nivel de píxel.

Las pruebas de procesamiento deben ser pequeñas. Descargar o procesar España completa en una única
petición está prohibido. Los artefactos aceptados se convierten a COG cuando procede y conservan
metadatos científicos y hashes.

El materializador solicita la AOI en EPSG:32630 a 10 m, impone un máximo de píxeles y selecciona la
escena L2A más reciente dentro de la ventana configurada con cloud cover de catálogo ≤30 %. Guarda
por separado el stack fuente y el stack de índices, y publica NDVI, NDMI y NBR solo después de
validar CRS, nodata, dimensiones, resolución y estructura COG.

## Sentinel-1

Fase 4 prepara catálogo, selección por AOI, metadata, temporalidad, footprint, polarización y
arquitectura de ingestión. No publica humedad, cambios ni productos avanzados sin correcciones SAR,
validación y una definición científica reproducible.

## Sentinel-3

Solo se incorporará cuando la resolución y el producto aporten valor explícito. No se remuestrea a
10 m para aparentar detalle inexistente.
