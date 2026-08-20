# Replay y consultas `as_of`

Replay reconstruye qué podía conocer VIGÍA en un instante T. Para geoespacial, un producto solo es
elegible cuando:

```text
observed_at <= T  (o no aplica)
processed_at <= T (o no aplica)
footprint cubre la consulta
availability ∈ {AVAILABLE, PARTIAL}
invalidated_at es nulo en el catálogo actual
```

Entre productos elegibles se usa la adquisición más reciente anterior a T para cada capa. Nunca se
usa Sentinel posterior a T ni un derivado procesado posteriormente. La misma regla se aplica a las
consultas SQL de cobertura y punto.

La fecha de adquisición, la de procesamiento y `as_of` son campos distintos. No se sustituye un
producto viejo por otro nuevo durante un Replay histórico. Las pruebas
`tests/geospatial/test_aoi_context.py` introducen productos futuros y comprueban que no aparecen.

Una capa ausente en T devuelve `UNAVAILABLE`/`NO DISPONIBLE`. La ausencia no se rellena con el valor
actual, interpolaciones ni valores de otra resolución.

Los productos invalidados se conservan para auditoría. La futura reconstrucción histórica de
supersesiones deberá considerar su intervalo `[published_at, invalidated_at)`; la API pública 4B
sirve el catálogo vigente y aplica estrictamente los dos límites temporales anteriores.

Fase 6 extiende este contrato a observaciones, meteorología e incidentes. El detalle técnico,
aislamiento y threat model están en `replay-engine.md` y `replay-data-leakage.md`. La pantalla
`/replay` mantiene una banda permanente, controles play/pausa/paso/velocidad y dos planos rotulados:
“LO QUE VIGÍA SABÍA” y, solo al activar comparación, “LO QUE SABEMOS AHORA”.

## Riesgo y forecast

`ANALYSIS` solo admite entradas observadas/procesadas hasta `as_of`. `FORECAST` exige
además `issued_at <= as_of`; `valid_at` puede ser posterior. Los tests rechazan cualquier
componente futura. Igual AOI, tiempos, hashes y configuración generan la misma clave.

El histórico AEMET diario inspeccionado no ofrece por sí solo las observaciones de mediodía local
que requiere FWI. En ese caso Replay muestra `UNAVAILABLE`; no inventa hora ni inicialización.
