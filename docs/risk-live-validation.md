# Validación LIVE de Fase 5

Fecha de ejecución: `2026-08-20`.

Un servicio HTTP accesible se registra por separado de la existencia y frescura de
productos. Los resultados de esta página son una fotografía de la ejecución indicada;
no garantizan disponibilidad futura. No se publican credenciales ni valores del entorno.

## Supabase / PostGIS

- Conexión PostgreSQL directa: `VERIFICADA`.
- Supabase Data API privilegiada: HTTP `200`.
- PostGIS: `3.3`, consulta espacial ejecutada correctamente.
- Migración Fase 5: aplicada una sola vez y verificada.
- Tablas: `risk_runs` y `risk_predictions`, `2/2`.
- Columnas nuevas: `7/7`; índices previstos: `6/6`; constraints encontrados: `14`.
- RLS forzado: `2/2` tablas de riesgo. Los roles `anon` y `authenticated` no pueden leerlas.
- Las tablas existentes de `vigia` conservaron RLS forzado; la vista pública de salud continúa
  separada de las observaciones internas.

## FIRMS y Fusion Engine

La consulta LIVE de España recibió `447` observaciones térmicas: NOAA-20 `130`, NOAA-21
`180`, SNPP `120` y MODIS `17`. La persistencia idempotente escribió `56` observaciones nuevas.
Son `OBSERVACIONES`, no incendios.

La ejecución de fusión con `as_of=2026-08-20T20:34:36Z` encontró `6` observaciones elegibles,
`2` clusters/candidatos y creó `2` incidentes en estado `VIGILANCIA`. La evidencia elegible de
esa ventana procedía únicamente de la familia `NASA_MODIS`. Ningún incidente fue promovido a
`INCENDIO_CONFIRMADO`.

## AEMET y FWI

- Observaciones convencionales LIVE: `9 699` recibidas y `3 459` nuevas persistidas.
- En un radio de 100 km de la AOI se encontraron `46` estaciones distintas en la base remota.
- Forecast horario municipal: HTTP correcto, `48` registros recibidos y `48` persistidos como
  `PRONOSTICADO`, con horas válidas entre `2026-08-20T12:00:00Z` y
  `2026-08-22T11:00:00Z`.
- El forecast horario no se marcó como apto para FWI diario: requiere agregación diaria
  normalizada y estado previo FFMC/DMC/DC.
- FWI VIGÍA: `NO DISPONIBLE` en esta ejecución porque no existía un estado diario previo
  verificable. El motor rechazó inicializarlo silenciosamente.

## Copernicus

- OAuth: `VERIFICADO`; reutilización de token verificada.
- Catálogo Sentinel-2 L2A: `5` productos encontrados para la consulta.
- Producto inspeccionado:
  `S2B_MSIL2A_20260818T110619_N0512_R137_T30TUK_20260818T132515.SAFE`.
- Adquisición: `2026-08-18T11:20:04.021Z`; nubosidad declarada: `2.21 %`.
- Process API: GeoTIFF real de prueba `64 x 64`, cuatro bandas, `EPSG:4326`, HTTP correcto.

## EUMETSAT

- OAuth con las credenciales disponibles: `RECHAZADO`.
- Catálogo anónimo: HTTP correcto; `35` productos en una ventana de seis horas.
- Colección observada: `Active Fire Monitoring (netCDF) - MTG - 0 degree`, producto real con
  intervalo de sensing `2026-08-20T20:10:00Z/2026-08-20T20:20:00Z`.
- Acceso al producto y lectura netCDF: `NO VERIFICADO` por el rechazo OAuth. No se descargó un
  volumen innecesario ni se interpretaron variables sin metadata verificable.

## EFFIS

- WMS GetCapabilities: HTTP `200`.
- Capa FWI publicada durante la verificación: `mf010.fwi`.
- GetMap de prueba para la AOI de Ávila: HTTP `200`, TIFF `64 x 64`, `EPSG:4326`, fecha
  `2026-08-20`, `4 096` píxeles válidos, rango aproximado `36.9611–45.5591`.
- EFFIS se conserva como benchmark externo. No hubo comparación cuantitativa ni calibración
  porque VIGÍA no produjo un índice numérico válido.

## Ejecución AOI

La AOI real de Fase 4B se centró en `40.651893, -4.697334` (Ávila). Se recuperaron terreno
oficial a `5 m`, índices Sentinel-2 de adquisición `2026-08-18` a aproximadamente `10 m` y land
cover oficial. LiDAR quedó `NO DISPONIBLE`.

La ejecución Fase 5 con `as_of=2026-08-20T10:00:00Z` encontró meteorología observada y contexto
de NDMI/pendiente, pero no estado previo FWI. Resultado:

- calidad: `INSUFFICIENT_DATA`;
- índice experimental: `null`;
- clase: `NO_DISPONIBLE`;
- razones: `FWI_PREVIOUS_STATE_UNAVAILABLE` e
  `INSUFFICIENT_COMPONENTS_FOR_COMPOSITE`.

La repetición con las mismas entradas devolvió el mismo identificador de predicción, verificando
idempotencia. No se publicó un COG de riesgo vacío o fabricado. La API devuelve HTTP `200` con
`availability=UNAVAILABLE` y conserva la evaluación y sus faltantes explícitos.

Como segunda provincia se consultó Segovia mediante su geometría administrativa oficial. No había
productos materiales para esa cobertura y la API respondió `UNAVAILABLE`, sin cambios de código.

## Límites de esta fotografía

- El índice VIGÍA es `EXPERIMENTAL`, no una probabilidad de incendio ni una predicción de
  ignición, comportamiento o propagación.
- La accesibilidad de una API no implica que existan observaciones o productos para una AOI.
- No se declara FWI operativo hasta disponer de una secuencia diaria, estado previo trazable y
  validación comparativa reproducible.
