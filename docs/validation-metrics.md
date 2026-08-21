# Definiciones de métricas científicas

| Métrica | Unidad/población | Definición | Elegibilidad y límites |
|---|---|---|---|
| Event recall | proporción de eventos positivos evaluables | TP/(TP+FN) | referencia temporal/espacial y oportunidad de sensor |
| Miss rate | proporción de eventos positivos evaluables | FN/(TP+FN) | complemento de recall sobre la misma población |
| Alert precision | proporción de incidentes VIGÍA evaluables | alertas asociadas/alertas evaluables | requiere referencia/control suficiente; ausencia de registro no es FP |
| F1 | media armónica | 2PR/(P+R) | solo si precision y recall comparten población |
| False alerts/day | incidentes por día | incidentes no asociados en cobertura evaluable/días | requiere espacio negativo defendible |
| False alerts/1.000 km²-day | incidentes por área-tiempo | FP·1000/(km²·día) | no usa “no-fire pixels” artificiales |
| Sensor observation latency | segundos | primera señal compatible − timestamp oficial compatible | no equivale a disponibilidad operacional FIRMS |
| Operational availability latency | segundos | primera disponibilidad operacional − referencia | `NO DISPONIBLE` sin timestamp de publicación/recepción histórico |
| Localization error | metros | primer centroide de incidente − punto inicial compatible | no usa centroide final/perímetro final sin explicación |
| Perimeter IoU/Hausdorff/area error | proporción/metros/hectáreas | geometrías temporalmente compatibles | requiere perímetro y tiempo compatibles |
| Risk discrimination | ranking/distribución | riesgo previo en fuegos vs controles comparables | Risk ≠ P(fire); exploratorio |
| Data coverage rate | proporción | casos con fuente disponible/casos del dataset | no es performance de Detection |

Todas las proporciones muestran N e intervalo Wilson 95 %. N<30 se marca
`INSUFFICIENT_SAMPLE`. PR-AUC, Brier, ECE y calibración son `NO DISPONIBLE` hasta disponer de una
salida continua/calibrada apropiada.

