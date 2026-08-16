# AEMET worker

El cliente implementa el flujo oficial de dos peticiones de observación convencional: obtiene la
URL temporal y descarga sus datos únicamente si continúa bajo `opendata.aemet.es`. Normaliza
temperatura, humedad, viento, dirección, racha, precipitación y presión como `OBSERVADO`; conserva
estación, coordenadas, timestamps, payload y la limitación de controles automáticos.

La persistencia es idempotente y crea `ingest_run`, health y provenance. No se ha realizado una
llamada real porque `AEMET_API_KEY` no está configurada.
