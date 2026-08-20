# Validación LIVE del corpus y Replay — 2026-08-20

Este documento solo debe contener comprobaciones ejecutadas. El estado previo a la materialización
del piloto es:

| Componente | Estado | Evidencia |
|---|---|---|
| Dataset JCyL | `API DISPONIBLE` | HTTP 200; 28.040 registros publicados, 17.739.671 bytes; años 2019–2026 en la respuesta inspeccionada. |
| FIRMS disponibilidad | `API DISPONIBLE` | Endpoint oficial respondió 200; Standard Processing disponible para MODIS desde 2000-11-01, SNPP desde 2012-01-20 y NOAA-20 desde 2018-04-01, según respuesta del día. |
| FIRMS histórico piloto | `PERSISTIDO` | El caso LOSACIO incorporó 589 NOAA-20 SP, 713 SNPP SP y 180 MODIS SP. Son observaciones dentro de una AOI amplia, no incendios ni una medida de latencia. |
| AEMET diario histórico | `API DISPONIBLE` | Consulta 2025-08-01..16 respondió 200 y 13.651 registros diarios. No es entrada FWI de mediodía. |
| Copernicus histórico | `UNAVAILABLE EN EL CORTE` | La consulta no produjo un producto Sentinel-2 con adquisición/publicación elegible antes del corte del caso; no se añadió ningún producto posterior. |
| EUMETSAT MTG | `NO DISPONIBLE` | OAuth continúa rechazado con `invalid_client`; MTG histórico no participa. |
| PostGIS Fase 6 | `VERIFICADO` | 7/7 tablas, 10/10 índices, RLS forzado 7/7, cero grants cliente de escritura, aislamiento LIVE y trigger de manifest inmutable. |
| Replay real persistido | `VERIFICADO` | Run final `3466811d-4678-4612-8b62-4693eb0d501c`, hash `1057b447…`, commit `acab51bb…`; 199 steps, determinista y `live_state_mutated=false`. |
| API Replay | `VERIFICADO` | `/health`, cases, run, timeline y observaciones respondieron; 0 observaciones en T0 y 1.482 al final, sin campos truth. |
| Suite unitaria/build | `GREEN` | Vitest 15/15, Pytest 128/128, TypeScript, ESLint, Next build, Ruff y mypy. |
| Playwright | `BLOCKED` | Chromium instalado, pero el sandbox denegó `MachPortRendezvousServer` con código 1100 antes de abrir página. |

Los conteos anteriores son resultados puntuales, no garantías de disponibilidad futura. Nunca
incluyen credenciales.

## Corpus y caso seleccionados

La política `historical-pilot-v1`, congelada antes de ejecutar el motor, normalizó 8.569 eventos y
seleccionó 12 eventos piloto con 554 versiones y 1.423 timestamps. El rango 0 fue LOSACIO (Zamora),
inicio oficial publicado `2022-07-17T16:00:00Z`, posición publicada `-6.039793, 41.711005`, 63
versiones y superficie máxima reportada 31.473,13 ha. La superficie es referencia posterior y nunca
entró al motor. No había perímetro oficial en esta fuente: `NO DISPONIBLE`.

## Resultado Replay real

- ventana: `2022-07-17T13:00:00Z` a `2022-07-18T22:00:00Z`, paso 10 minutos;
- 1.482 inputs térmicos Standard Processing y 199 steps;
- estados vistos: `VIGILANCIA`, `ANOMALIA`, `PROBABLE_INCENDIO`;
- `INCENDIO_CONFIRMADO`: 0, bloqueado por la máquina de estados;
- riesgo: `UNAVAILABLE` en todos los steps; 126 registros AEMET diarios relevantes quedaron
  `PARTIAL_DATE_ONLY_NOT_FWI_READY` y no se convirtieron en FWI;
- wall time del motor: 206.434 ms; pico aproximado `tracemalloc`: 12.685.477 bytes;
- estado canónico LIVE mutado: `false`.

El run final con checkpoint por step registró 613.320 ms y pico aproximado 12.693.773 bytes. No es
directamente comparable con el run inicial: incluye serialización/reemplazo atómico del historial
completo de steps. Una segunda invocación reanudó desde el step 198, devolvió el mismo run ID y no
creó duplicados: una fila por `run_hash`, 199 steps y los 199 `output_hash` idénticos al run inicial.
La serialización completa por step es una limitación de rendimiento conocida; un formato
incremental queda `EN PREPARACIÓN`.

El matching se ejecutó solo después del Replay con
`evaluation-spatiotemporal-v1` (15 km, 48 h): 7 incidentes Replay únicos, 2 compatibles con la
referencia bajo ese criterio. El primero tenía observación inicial `2022-07-17T21:23:00Z`, distancia
4.783,30 m y diferencia temporal absoluta 19.380 s respecto al inicio oficial. Esto **no es una
latencia**: FIRMS Archive no expone la hora original de publicación y los inputs están marcados
`OBSERVATION_TIME_PROXY`. Un solo caso no produce métricas de precisión, recall ni cobertura.
