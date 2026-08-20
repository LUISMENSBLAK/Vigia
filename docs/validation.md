# Validación científica

No se publica ninguna métrica sin `validation_run` reproducible. Cada ejecución conserva commit,
modelo, dataset hash, periodo, regiones, seed, configuración, tamaño de muestra y resultados.

## Separación

- train, validation y test independientes;
- separación temporal y espacial cuando sea viable;
- temporadas completas y regiones no vistas reservadas;
- walk-forward para evaluación temporal;
- reloj de replay que impide acceder a `timestamp > replay_time`.

## Métricas

Detección: precision, recall, F1, FPR, FNR, PR-AUC y matriz de confusión. Calibración: Brier,
curva de calibración y ECE. Localización: mediana, P90/P95 y distancia a origen/perímetro.
Propagación: IoU, Hausdorff cuando proceda, área, dirección, velocidad y cobertura probabilística.
Tiempo: primera observación, alerta, probable y confirmado.

El objetivo de investigación de precision ≥99,9 % para `INCENDIO_CONFIRMADO` no es una métrica del
sistema. Solo podría publicarse tras un test independiente suficientemente grande, junto a N,
intervalo de confianza, recall, dataset, periodo y versión.

## Puertas de Fase 3

Las pruebas sintéticas validan geodistancia, ventanas, clustering, determinismo, idempotencia,
persistencia temporal, contradicciones, transiciones y no leakage con `as_of`. No validan precisión
científica. Antes de calibrar deben prepararse positivos, negativos, fuentes térmicas recurrentes y
separaciones espaciales/temporales reales. Ningún resultado sintético aparece en la API LIVE.
