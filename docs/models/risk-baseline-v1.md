# Model card — risk-baseline-v1

## Identidad y uso previsto

- Tipo: reglas deterministas y fórmulas publicadas; no ML.
- Estado: `EXPERIMENTAL`.
- Validación operacional: `UNVALIDATED`.
- Salida: índice descriptivo ambiental 0–100 o `NO DISPONIBLE`.
- Configuración: `config/risk/risk-baseline-v1.json`.

Sirve para investigación, auditoría y comparación reproducible de contexto ambiental en
AOIs españolas. No está autorizado como probabilidad, alerta pública, predicción de
ignición, confirmación de incendio o motor de propagación.

## Entradas y composición

FWI 1987 con estado histórico válido, NDMI Sentinel-2 enmascarado, pendiente IGN MDT05 y
cobertura oficial como contexto. Media no ponderada de componentes disponibles;
`fire_weather` es obligatorio y se requieren al menos dos. Faltantes no se imputan.

## Validación actual

- FWI: regresión contra tabla oficial NRCan NOR-X-424.
- Determinismo, rangos, nodata, alineación, CRS, idempotencia contractual y fuga temporal:
  pruebas automatizadas.
- Calibración contra incendios históricos, exactitud, AUC o probabilidades: `NO VERIFICADO`.

## Riesgos y limitaciones

Las escalas y bandas son decisiones de ingeniería versionadas, no umbrales operacionales.
IDW no resuelve microclimas. La vegetación puede estar obsoleta o cubierta por nubes.
Land cover no equivale a combustible. FWI necesita continuidad diaria y validación regional.

## Replay histórico

El baseline puede ejecutarse con `ReplayClock` y contexto cortado por `as_of` sin modificar la
composición. El estado FWI se recupera por estación únicamente si `observed_at <= as_of`; un warm-up
encadena FFMC/DMC/DC con meteorología compatible. La inicialización estacional NRCan se etiqueta
`INITIALIZED_NOT_OBSERVED` y solo procede si constan criterios de nieve. El histórico diario AEMET
sin observación de mediodía local no se transforma en una entrada FWI inventada.

Estas capacidades mejoran la reproducibilidad, no validan el modelo. Hasta disponer de corpus
representativo, controles, splits inmutables y métricas fuera de muestra, el estado permanece
`EXPERIMENTAL / UNVALIDATED` y el resultado no es probabilidad ni recomendación operativa.
