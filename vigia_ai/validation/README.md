# VIGÍA Scientific Validation Engine

Este paquete evalúa salidas ya producidas por Replay/Fusion/Detection contra referencias
históricas separadas. Nunca participa en la detección, nunca entrega ground truth al replay y
nunca habilita `INCENDIO_CONFIRMADO`.

Contratos centrales:

- datasets y splits congelados, versionados y con hash;
- separación `DEVELOPMENT` / `VALIDATION` / `TEST` por grupos de episodio;
- acceso a `TEST` explícito y auditable;
- matching versionado y análisis de sensibilidad preespecificado;
- elegibilidad por métrica con códigos de exclusión;
- métricas con N, incertidumbre y estado `NO_DISPONIBLE`/`INSUFFICIENT_SAMPLE`;
- reportes JSON deterministas y verificables.

El Risk Baseline se analiza por separado y nunca se interpreta como probabilidad de ignición.
