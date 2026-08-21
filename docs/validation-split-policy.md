# Política de split de validación

Versión: `validation-temporal-group-split-v1`.

1. La asignación ocurre antes de consultar rendimiento VIGÍA.
2. Solo entran positivos `HIGH` con coordenadas y tiempo oficial de minuto/exacto; los controles
   requieren evidencia externa y una política propia.
3. Se construye `event_group_id` mediante componentes temporoespaciales: eventos de la misma
   región y provincia se unen si están a ≤25 km y ≤72 h. El algoritmo es determinista.
4. Los grupos se ordenan por su primer timestamp. Se asigna aproximadamente 60/20/20 a
   DEVELOPMENT/VALIDATION/TEST sin dividir un grupo.
5. Esta separación temporal reduce correlación y reserva el periodo posterior como test futuro.
6. El manifest congelado enumera cada caso, grupo y split, y conserva dataset hash/split hash.
7. La lista TEST no se entrega al motor durante desarrollo. El acceso requiere candidato congelado
   y auditoría persistida.

La diversidad por región, vegetación, tamaño y era de sensores se informa, pero no se fuerza
mediante intercambio posterior de casos. Eso evitaría seleccionar el split mirando resultados.

