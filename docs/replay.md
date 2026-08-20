# Replay y consultas `as_of`

Replay reconstruye qué podía conocer VIGÍA en un instante T. Para geoespacial, un producto solo es
elegible cuando:

```text
observed_at <= T  (o no aplica)
processed_at <= T (o no aplica)
footprint cubre la consulta
availability ∈ {AVAILABLE, PARTIAL}
```

Entre productos elegibles se usa la adquisición más reciente anterior a T para cada capa. Nunca se
usa Sentinel posterior a T ni un derivado procesado posteriormente. La misma regla se aplica a las
consultas SQL de cobertura y punto.

La fecha de adquisición, la de procesamiento y `as_of` son campos distintos. No se sustituye un
producto viejo por otro nuevo durante un Replay histórico. Las pruebas
`tests/geospatial/test_aoi_context.py` introducen productos futuros y comprueban que no aparecen.

Una capa ausente en T devuelve `UNAVAILABLE`/`NO DISPONIBLE`. La ausencia no se rellena con el valor
actual, interpolaciones ni valores de otra resolución.
