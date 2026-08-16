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
