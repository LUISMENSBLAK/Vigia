# VIGÍA Risk Engine — baseline nacional v1

## Alcance

`risk-baseline-v1` describe condiciones ambientales que pueden favorecer la ignición o
el desarrollo inicial. Es `EXPERIMENTAL`: no es una probabilidad, no detecta fuego, no
confirma incendios y no constituye una alerta operativa. NASA FIRMS y los incidentes de
Fase 3 están excluidos de las entradas causales para evitar fuga entre riesgo y detección.

La unidad de ejecución es una AOI/tile configurable. No existe código específico para
Ávila. El mismo contrato admite bbox, GeoJSON, unidad administrativa o geometría PostGIS.

## Componentes

- `fire_weather`: FWI 1987 únicamente cuando existe una secuencia diaria válida y estado
  FFMC/DMC/DC anterior. La meteorología interpolada conserva estaciones, distancias,
  método IDW, edad y resolución efectiva. Una previsión sin precipitación acumulada no
  es compatible con FWI.
- `vegetation`: sequedad descriptiva derivada de NDMI en píxeles válidos. NDVI y NBR se
  conservan como contexto. Se mantienen fecha, máscara SCL, nodata y resolución.
- `terrain`: pendiente normalizada como contexto estático. Elevación y orientación se
  exponen, pero v1 no pretende modelar propagación.
- `land_cover`: contexto oficial. No aporta puntuación en v1 y nunca se denomina modelo
  de combustible.

## Composición experimental

Cada componente numérica se expresa en una escala descriptiva de 0–100. V1 usa la media
aritmética sin pesos de las componentes disponibles para evitar pesos ocultos. Requiere
`fire_weather` y al menos dos componentes. En caso contrario, el índice es nulo y la
calidad es `INSUFFICIENT_DATA`.

Las bandas 0–20, 20–40, 40–60, 60–80 y 80–100 son bandas de presentación versionadas;
no son frecuencias observadas, probabilidades ni umbrales operacionales validados.

## Contrato temporal

- `ANALYSIS`: `valid_at = as_of`, horizonte 0.
- `FORECAST`: `valid_at >= as_of`, horizonte real máximo 240 h.
- Ninguna entrada con `observed_at`, `processed_at` o `issued_at` posterior a `as_of`
  puede participar.
- Cada salida conserva versión, configuración, snapshot/hash de entrada, resolución,
  razones, faltantes y hash de salida.

## Raster, CRS y cobertura nacional

Los componentes deben coincidir en CRS, transform, dimensiones y resolución. No existe
remuestreo implícito. Los píxeles inválidos siguen siendo nodata. Se publican dos COG:
`RISK_BASELINE` y `RISK_DATA_QUALITY`. PostGIS conserva huella, metadata y provenance.

Se usa ETRS89/UTM 29–31 para Península, Baleares, Ceuta y Melilla según huso;
REGCAN95/UTM 28N (EPSG:4083) para Canarias. La API transforma a EPSG:4326.

## API

- `GET /api/risk/current`
- `GET /api/risk/context`
- `GET /api/risk/forecast`
- `GET /api/risk/layers`

Una respuesta sin ejecución real persiste como `UNAVAILABLE`; nunca se rellena con una
estimación sintética.
