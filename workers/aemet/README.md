# AEMET worker

El cliente implementa el flujo oficial de dos peticiones de observación convencional: obtiene la
URL temporal y descarga sus datos únicamente si continúa bajo `opendata.aemet.es`. Normaliza
temperatura, humedad, viento, dirección, racha, precipitación y presión como `OBSERVADO`; conserva
estación, coordenadas, timestamps, payload y la limitación de controles automáticos.

La persistencia es idempotente y crea `ingest_run`, health y provenance. El cliente también
normaliza la predicción horaria municipal como `PRONOSTICADO`, manteniendo precipitación horaria
separada de su probabilidad de intervalo. La marca `fwi_compatible` permanece falsa hasta que
exista una agregación diaria científicamente definida y un estado previo FFMC/DMC/DC.

La comprobación LIVE del `2026-08-20` recibió `9 699` observaciones convencionales y persistió
`3 459` nuevas. La consulta horaria municipal recibió y persistió `48` periodos. Son resultados
históricos de esa ejecución, no una promesa de disponibilidad futura; véase
`docs/risk-live-validation.md`.
