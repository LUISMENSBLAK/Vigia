# Metodología de IA

## Riesgo no es detección

Risk Engine estima condiciones favorables a la ignición. Detection Engine clasifica evidencia de
fuego activo. Fusion/Confidence combina evidencia sin convertir por umbral una probabilidad alta
en `INCENDIO_CONFIRMADO`.

## Baselines

Cada motor comienza con un baseline interpretable. Se compararán regresión logística, árboles y
gradient boosting antes de justificar redes profundas. La calibración se evaluará fuera de muestra.
SHAP o importancias solo se publicarán junto con el modelo, versión y limitaciones pertinentes.

## Datos de entrenamiento

Detection Engine necesita incendios, observaciones negativas, industria, superficies calientes,
quemas controladas etiquetadas y ruido. No se permite entrenar únicamente con positivos. El código
reutilizable vive en módulos; notebooks solo documentan exploración y llaman esos módulos.

## Propagación

La primera versión será físico-estadística y experimental. Generará ensembles, P10/P50/P90 y mapas
de probabilidad de afectación. Toda salida llevará: `PREDICCIÓN EXPERIMENTAL — NO USAR PARA
DECISIONES OPERATIVAS` hasta completar una validación apropiada.

## Baseline de fusión y detección

Fusión usa distancia geodésica, ventanas temporales, resolución, familias, persistencia y contexto.
Detection devuelve estados, reason codes y `evidence_strength` discreta. Esta fuerza no es una
probabilidad calibrada. `INCENDIO_CONFIRMADO` no puede ser emitido automáticamente. Confidence
recibe un `EvidenceBundle`, continúa en research y obliga `calibrated_probability = null`.

## Risk baseline v1

No usa ML. El FWI procede de ecuaciones publicadas y la composición es una regla
determinista, no calibrada y experimental. No se declara probabilidad, precisión ni
confianza estadística. Véanse `risk-engine.md` y la model card.

## Evaluación histórica

Replay no entrena ni modifica los motores. El evento oficial se oculta durante la ejecución y el
matching espacio-temporal ocurre después, en un módulo de evaluación separado. La política del
corpus se congela antes de ver resultados. No hay métricas científicas de Fase 6 mientras no existan
positivos y controles representativos, splits inmutables y timestamps de disponibilidad defendibles.

Fase 7 materializa esos contratos sin entrenar: corpus y split se congelaron antes del baseline,
matching primario y sensibilidad se preespecificaron, y TEST queda detrás de una auditoría. El
primer ValidationRun solo dispone de N=1 evaluable y cero controles; por eso recall, latencia y
localización son `INSUFFICIENT_SAMPLE`, mientras precision, F1, calibración y falsas alertas son
`NO DISPONIBLE`. El resultado no autoriza cambios caso por caso ni claims operacionales.
