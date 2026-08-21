# ValidationRun real — baseline científico v1

Ejecución UTC: `2026-08-21T01:37:24Z`. Estado: `VALIDACIÓN EXPERIMENTAL`.

## Identidad reproducible

- commit ejecutado: `30abbf9b45fd8ae1f98ad963e1e95d392bbe98e9`;
- dataset: `historical-corpus-jcyl-high-v1`;
- dataset hash: `89606f6395cdabe05f47311e022b1e6c52474f2cc10ffe622078db0c66985256`;
- split: `validation-split-v1`;
- split hash: `610aa6230c51d8b2f94405aff959b8d5e5eb15fe22d8f1e03d60aed6915503cf`;
- split ejecutado: `DEVELOPMENT`;
- run id: `a1930dd1-c19f-4189-adb1-dfe6f2c6941e`;
- run key: `f3f0a6d2de170f3713c86c10ba3ee67afe33a7e2b3f48f3c202582ee702005b0`;
- report hash: `9df58b3f7cc75946b6bb43998f54017fc69ee9cb789fed011ba380679f837c67`;
- TEST accedido: no;
- estado LIVE mutado: no.

La misma orden, con los mismos artefactos y timestamp, se ejecutó dos veces. Ambas devolvieron el
mismo run id, run key y report hash; no se duplicó el ValidationRun.

## Muestra realmente evaluada

El manifest conserva 5.866 referencias `HIGH` de la fuente oficial de Castilla y León entre 2021
y 2026. El split DEVELOPMENT contiene 3.520. Solo una de esas referencias tenía un Replay
materializado, por lo que 3.519 quedaron excluidas de métricas de detección por `NO_REPLAY_OUTPUT`.

Para el único evento evaluable hubo una asociación uno-a-uno a `PROBABLE_INCENDIO`. Esto produce
TP=1 y FN=0 en N=1, pero el resultado se publica como `INSUFFICIENT_SAMPLE`, no como recall 100 %.
El intervalo Wilson 95 % para esa fracción es [0,2065; 1,0000], demasiado amplio para un claim.
Latencia de observación y error de localización también quedan `INSUFFICIENT_SAMPLE` con N=1.

La cobertura de materialización de Replay fue 1/3.520 (0,0284 %; Wilson 95 % aproximado
0,0050 %–0,1608 %). Esta cifra mide cobertura del experimento, no rendimiento de VIGÍA.

## Métricas no calculables

El corpus v1 contiene cero ventanas de control respaldadas. Por tanto son `NO DISPONIBLE`:

- alert precision, F1 y carga de falsas alertas;
- PR-AUC, ROC-AUC, Brier, ECE y calibración;
- discriminación del Risk Engine;
- latencia de disponibilidad operacional histórica;
- IoU, Hausdorff y error de área de perímetro.

Cuatro incidentes Replay alcanzaron el umbral probable dentro del caso materializado. Los no
asociados no se etiquetan como falsos positivos porque no existe cobertura de control que permita
descartar incendios o fuentes térmicas reales en el espacio-tiempo evaluado.

## Base de datos y API

La migración remota Fase 7 creó nueve tablas nuevas. La comprobación remota confirmó 10/10 tablas
de validación con RLS forzado, cero grants de escritura a `anon`/`authenticated`, seis triggers de
inmutabilidad/TEST y cero runs TEST sin auditoría.

Los contratos de los seis endpoints de validación pasaron las pruebas API. El smoke HTTP con la
base real quedó `BLOCKED` antes de arrancar FastAPI por un timeout local al leer una dependencia del
entorno virtual (`Errno 60`); no se clasifica como fallo funcional ni como verificación HTTP real.
