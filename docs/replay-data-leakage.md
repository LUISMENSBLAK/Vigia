# Prevención de data leakage en Replay

## Amenazas

1. observación o producto adquirido después de `as_of`;
2. producto observado antes pero publicado/procesado después;
3. perímetro final, área, estado u hora oficial entrando al motor;
4. estado FWI futuro o forecast emitido después del corte;
5. matching con el evento oficial usado para formar incidentes;
6. reloj de pared consultado por un componente interno;
7. salida Replay alterando el estado LIVE.

## Controles

- reloj único inyectado y acotado;
- doble corte `observed_at`/`available_at`;
- truth firewall recursivo en `ReplayInput`;
- contextos de inputs y referencia con tipos incompatibles;
- módulo `evaluation.py` separado que ReplayEngine no importa;
- tablas replay privadas con RLS forzado y sin FK hacia incidentes LIVE;
- constraint permanente `live_state_mutated = false`;
- reason codes explícitos: `FUTURE_OBSERVATION`, `NOT_YET_AVAILABLE` y mismatch temporal;
- comparación UI apagada por defecto.

## Suite adversarial

Las pruebas inyectan observación térmica, weather, Sentinel procesado y perímetro oficiales
posteriores al corte; comprueban que no entran. Un caso positivo sin inputs produce cero evidencia,
cero incidentes y riesgo `UNAVAILABLE`, aunque exista referencia oficial. Dos ejecuciones con
inputs en orden inverso deben producir exactamente los mismos hashes y steps. Ninguna prueba
sintética se presenta como validación científica.

## Límites

`OBSERVATION_TIME_PROXY` de FIRMS Archive no reconstruye la latencia real de publicación. Por ello
el replay piloto puede estudiar detección retrospectiva, pero no afirmar latencia operacional. La
auditoría de dependencias que invoquen `datetime.now()` debe repetirse al añadir motores.
