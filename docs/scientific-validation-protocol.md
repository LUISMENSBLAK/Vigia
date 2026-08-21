# Protocolo científico de validación VIGÍA v1

Estado: `VALIDACIÓN EXPERIMENTAL`. Congelado antes del primer ValidationRun de Fase 7.

## Pregunta y unidades

VIGÍA evalúa cuatro sistemas distintos: Detection, Fusion, Replay y el Risk Baseline. La unidad
primaria de Detection es el evento de referencia; la de carga operacional es el incidente VIGÍA;
la de falsas alertas es área-tiempo. No se mezclan observaciones, alertas, eventos y píxeles.

El endpoint primario futuro de `PROBABLE_INCENDIO` es: evento oficial evaluable asociado a al
menos un incidente VIGÍA que alcance ese estado. `INCENDIO_CONFIRMADO` permanece deshabilitado.
La meta futura de precision ≥99,9 % es un objetivo de investigación, no un resultado.

## Dataset y referencia

Un positivo requiere existencia documentada, coordenadas y tiempo oficial con precisión de minuto
o mejor. La referencia JCyL se clasifica `HIGH` bajo este contrato, aunque el punto siga siendo una
localización oficial aproximada. Los eventos con referencia insuficiente se conservan en el corpus
histórico, pero no entran en este dataset evaluable.

MITECO/EGIF y EFFIS/Copernicus se catalogan como fuentes externas. EFFIS no es verdad absoluta.
El paquete RDF nacional EGIF 1983–2015 inspeccionado no enlaza una fecha de incendio a sus 509.593
registros; por eso no se usa para latencia ni Replay sin otra fuente temporal compatible.

## Split preespecificado

Los episodios se agrupan antes de evaluar VIGÍA: misma región/provincia, separación ≤25 km y
≤72 h. Los grupos se ordenan temporalmente y se reservan aproximadamente 60 % DEVELOPMENT,
20 % VALIDATION y el 20 % cronológicamente posterior para TEST. El corte se realiza únicamente en
fronteras de grupo. El manifest materializa todos los IDs y su hash.

TEST queda congelado. Solo puede abrirse para una configuración candidata ya congelada, con actor,
motivo, fecha y registro de auditoría. Fase 7 no usa TEST para ajustar reglas ni thresholds.

## Baseline y matching

`VIGÍA Detection Baseline v1` es exactamente Fusion/Detection de Fase 6 en commit
`73d157d907a0f3a377f8866ff6bd4eff4400c78c`; configuración Fusion
`297ccbc534daff66a9c8d94b1f4252c272f7eac7999db08427827a3f83b72314`.

El matcher primario v1 usa 10 km/24 h y asignación uno-a-uno determinista. Esta elección se congeló
antes del ValidationRun, no porque produjera la métrica más favorable. El análisis de sensibilidad
preespecificado combina 5/10/15 km y 24/48 h. Fragmentación y fusión se informan aparte.

## Métricas primarias y secundarias

- Primaria futura: recall event-level a `PROBABLE_INCENDIO`, con TP, FN, N e intervalo Wilson.
- Operacionales: precision alert-level y falsas alertas por día y 1.000 km²-día, solo con espacio
  negativo suficientemente referenciado.
- Secundarias: primera señal por estado, latencia de observación, error de localización y
  estratos de tamaño, región, sensor, día/noche, terreno y meteorología cuando N lo permita.
- F1 solo existe si precision y recall comparten una población científicamente compatible.
- Accuracy no es headline por el fuerte desequilibrio de clases.

PR-AUC, ROC-AUC, Brier, ECE y curvas de calibración quedan `NO DISPONIBLE`: VIGÍA no produce una
probabilidad calibrada. Risk es un índice ambiental compuesto, no P(incendio).

## Censura, latencia y perímetros

La elegibilidad se decide por métrica. Fecha sin hora produce intervalo censurado o
`INSUFFICIENT_TEMPORAL_PRECISION`. FIRMS Standard Processing aporta tiempo de observación; no
demuestra disponibilidad operacional histórica. Esa latencia permanece `NO DISPONIBLE`.

IoU, Hausdorff y error de área exigen perímetros temporalmente compatibles. Nunca se compara un
punto inicial con un perímetro final como si midiera propagación.

## Incertidumbre y muestra pequeña

Las proporciones usan Wilson bilateral 95 %. Mediana y cuantiles podrán usar bootstrap por grupo
de episodio, semilla 20260820 y 2.000 iteraciones. Un estrato con N<30 muestra counts e intervalo,
pero no publica porcentaje: `INSUFFICIENT_SAMPLE`. N=1 nunca se extrapola a una región.

Con cero fallos no se afirma 100 % demostrado; se muestra el límite inferior. Un claim extremo
requiere cálculo de potencia/tamaño muestral previo.

## Integridad y reproducibilidad

Todo run registra dataset/split/commit/config/matcher, hashes, counts, exclusiones y limitaciones.
Mismos artefactos congelados producen el mismo run key y las mismas métricas. Un informe publicado
es inmutable. Una corrección respaldada crea una nueva versión; nunca se edita silenciosamente.

