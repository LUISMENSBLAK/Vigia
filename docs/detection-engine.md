# Detection Engine — reglas conservadoras

Estado: `EXPERIMENTAL`. Transforma un candidato en recomendación de estado y reason codes; no
produce `calibrated_probability`.

## Estados

- `VIGILANCIA`: evidencia aislada o caducada.
- `ANOMALIA`: al menos dos observaciones compatibles.
- `POSIBLE_IGNICION`: persistencia y número mínimo de detecciones.
- `PROBABLE_INCENDIO`: persistencia, calidad, cuatro observaciones y dos familias térmicas, sin
  contradicción registrada.
- `INCENDIO_CONFIRMADO`: bloqueado para automatización.
- `DESCARTADO`: reservado a evidencia contradictoria explícita sin confirmación térmica suficiente.

La máquina de estados prohíbe saltos. Una nueva recomendación recorre y registra cada transición;
`SIN_EVIDENCIA → INCENDIO_CONFIRMADO` genera error. Los estados pueden degradarse o descartarse sin
borrar historial.

## Reason codes

`MULTI_SENSOR_AGREEMENT`, `MULTI_FAMILY_AGREEMENT`, `TEMPORAL_PERSISTENCE`,
`SPATIAL_CONSISTENCY`, `FRP_INCREASE`, `SINGLE_OBSERVATION`, `SOURCE_CONTRADICTION`,
`KNOWN_HEAT_SOURCE`, `STALE_DATA`, `LOW_QUALITY` e
`INSUFFICIENT_INDEPENDENT_EVIDENCE`.

Los textos “¿Por qué este estado?” se generan desde conteos y métricas, no mediante un LLM.
`evidence_strength` usa categorías discretas de `MUY_BAJA` a `MUY_ALTA`; no es una probabilidad,
no se promedia confidence de sensores y no se muestra ningún porcentaje.

## Expiración

La antigüedad se evalúa contra `as_of`. Un candidato pasado de la ventana configurada recibe
`STALE_DATA`, no puede elevarse y registra `inactive_at`. Los registros permanecen para replay,
provenance y auditoría.
