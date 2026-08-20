# Motor Replay histórico

## Contrato

`ReplayClock` genera una secuencia cerrada entre `replay_start` y `replay_end`. `ReplayDataContext`
solo entrega inputs con `observed_at <= as_of` y `available_at <= as_of`. Todos los timestamps
requieren zona horaria. El motor llama a los mismos `fuse_observations`, reglas de detección y
máquina de estados que LIVE; no existe un algoritmo privilegiado para casos históricos.

```text
referencias oficiales ──> TruthReferenceContext ──> evaluación posterior
                                             ╳
inputs disponibles ────> ReplayDataContext ──────> Fusion/Detection/Risk
```

El cruce está prohibido durante la ejecución. `ReplayInput` rechaza campos de perímetro, área
quemada, estado final u origen oficial incluso anidados. `vigia.replay_*` no escribe
`vigia.incidents`, `fire_observations` ni el estado canónico LIVE; la base fuerza
`live_state_mutated = false`.

## Entradas históricas

- FIRMS Standard Processing: el archivo no publica el timestamp original de disponibilidad. Se
  usa `observed_at` como límite inferior explícito (`OBSERVATION_TIME_PROXY`) y se prohíben claims
  de latencia. NASA recomienda Standard Processing, no NRT, para series temporales.
- AEMET diario: conserva fecha, estación y valores publicados. Es `DATE_ONLY` y no satisface por sí
  solo las entradas de mediodía local del FWI.
- Sentinel/terreno/land cover: solo entran si adquisición y publicación/procesamiento no son
  posteriores al corte. Un año de referencia estático posterior se marca `TEMPORAL_MISMATCH`.

## FWI histórico

El estado FFMC/DMC/DC es encadenado por estación. `FWIStateStore.latest(as_of=T)` nunca devuelve un
estado posterior. Se exige warm-up suficiente y lluvia acumulada válida. La inicialización oficial
de temporada con nieve (FFMC=85, DMC=6, DC=15), descrita por
[NRCan](https://cwfis.cfs.nrcan.gc.ca/index.php/background/dsm/fwi), solo se permite con criterios
de nieve conocidos y queda marcada `INITIALIZED_NOT_OBSERVED`. Sin condiciones compatibles, el
riesgo devuelve `UNAVAILABLE`.

## Determinismo, reanudación y caché

Manifest, inputs, configuración y commit forman hashes canónicos. Reordenar entradas no cambia la
salida. Casos e inputs usan claves únicas; runs usan `run_hash`; steps usan `(run, step_index)`.
`run_phase6_replay.py` escribe cada step mediante reemplazo atómico en `data/cache`, ignorado por
Git. Al reanudar valida manifest, configuración y commit, reconstruye el último estado derivado y
continúa desde el siguiente step. `completed_step` conserva el progreso remoto al persistir. Los
clientes históricos reutilizan identificadores, checksums y cachés; nunca guardan tokens.

## API

- `GET /api/replay/cases`
- `GET /api/replay/cases/{case_id}`
- `POST /api/replay/runs`
- `GET /api/replay/runs/{run_id}`
- `GET /api/replay/runs/{run_id}/timeline`
- `GET /api/replay/runs/{run_id}/incidents`
- `GET /api/replay/runs/{run_id}/observations?as_of=T`

`POST` ejecuta de forma síncrona el piloto acotado. Una cola persistente para runs nacionales
largos queda `EN PREPARACIÓN`; el esquema ya conserva estado, errores y progreso.
