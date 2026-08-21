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

## Fase 5

La suite incluye referencia oficial FWI, estado encadenado, IDW/edad, future leakage,
composición incompleta, rangos, alineación/resolución, nodata/COG, CRS nacionales,
migración RLS y contratos API. La ejecución LIVE se registra por separado.

En la validación final del `2026-08-20`: TypeScript, ESLint, Vitest (`12/12`), Next.js build,
Ruff, mypy y Pytest (`104/104`) terminaron correctamente. Playwright quedó `BLOCKED`: Chromium
estaba instalado, pero el sandbox del entorno denegó el registro del puerto Mach necesario para
arrancarlo. No se clasifica como fallo funcional de VIGÍA.

## Puertas de Fase 6

La suite añade ingestión/identidad/deduplicación histórica, precisión temporal, manifest y reloj,
clock injection, `as_of`, truth firewall, leakage térmico/weather/Sentinel/perímetro, warm-up FWI,
aislamiento LIVE, confirmación automática bloqueada, determinismo, contratos SQL/RLS, API/timeline
y presentación textual. El primer replay real debe informar su muestra y límites; un caso no valida
precisión, recall, latencia ni cobertura nacional.

Validación final Fase 6 del `2026-08-20`: TypeScript, ESLint, Vitest (`15/15`), build Next.js,
Ruff, mypy (`69` módulos) y Pytest (`128/128`) terminaron GREEN. La cadena completa de migraciones
se ejecutó desde cero en PostgreSQL 17/PostGIS 3.5 desechable; la mutación de un manifest congelado
fue rechazada por trigger. Playwright se intentó con dos casos, pero Chromium no pudo registrar
`MachPortRendezvousServer` por el sandbox (`Permission denied 1100`): `BLOCKED`, no fallo funcional.

## Fase 7

El protocolo, baseline, matcher y split por grupos se congelan antes de evaluar. DEVELOPMENT,
VALIDATION y TEST no comparten event groups; TEST exige acceso auditado. La elegibilidad es por
métrica y nunca elimina silenciosamente una referencia del corpus. Una muestra pequeña conserva
counts e intervalo, pero oculta el porcentaje como `INSUFFICIENT_SAMPLE`.

El primer run real de DEVELOPMENT materializó 1 de 3.520 referencias y no incluyó controles. Por
ello no soporta un claim de recall y no permite precision, F1 ni falsas alertas. El informe exacto
está en `reports/baseline-validation-v1.json`; interpretación en `validation-live-results.md` y
límites en `validation-limitations.md`.

Antes del commit de implementación terminaron GREEN TypeScript, ESLint, Vitest (`18/18`), build
Next.js, Ruff, mypy (`86` módulos) y Pytest (`147/147`). Tras corregir el contrato JSONB descubierto
por la ejecución remota, Ruff volvió a terminar GREEN y el ValidationRun real completó dos veces
con identidad estable. Las repeticiones finales de TypeScript, mypy, Pytest y el smoke HTTP quedaron
`BLOCKED` por timeouts de lectura del volumen/entorno virtual local, sin diagnóstico de código.
Playwright quedó `BLOCKED`: los tres Chromium fueron rechazados por
`MachPortRendezvousServer` (`Permission denied 1100`) antes de ejecutar tests.
