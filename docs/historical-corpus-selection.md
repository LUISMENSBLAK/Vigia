# Política de selección del corpus piloto

Versión: `historical-pilot-v1`.

## Regla congelada antes de evaluar

1. Incluir solo referencias oficiales con calidad `HIGH`, posición publicada y hora de inicio con
   precisión al menos de minuto.
2. Exigir superficie máxima reportada igual o superior a 50 ha para el piloto positivo inicial.
3. Estratificar por año y provincia; escoger primero el mayor evento reportado de cada estrato.
4. Completar el límite con los mayores restantes, usando `event_key` como desempate estable.
5. Elegir el demostrador por `pilot-rank` dentro de esa lista, nunca por el resultado del motor.

La política no mira número de hotspots, detecciones, estados, tiempos de respuesta ni riesgo. Así
evita escoger únicamente el caso que “funciona”. El manifiesto registra versión de política,
hashes, ventana, AOI, fuentes y disponibilidad de sensores.

## Controles y splits

Los controles `CONTROL_NO_KNOWN_FIRE` todavía no se materializan: la ausencia de una referencia no
demuestra ausencia de fuego. Antes de crear negativos se cruzarán EGIF/EFFIS/regionales, fuentes de
calor conocidas y cobertura de sensores. Los splits train/validation/test permanecen
`EN PREPARACIÓN`; Fase 6 no entrena ML y no publica métricas.

## Sesgos conocidos

- cobertura regional desigual y cambios de formulario;
- incendios pequeños o sin posición subrepresentados por el filtro piloto;
- superficie final conocida después del inicio;
- nubosidad, órbitas, saturación y cobertura temporal de cada sensor;
- FIRMS Archive no expone el timestamp histórico original de publicación;
- meteorología diaria no equivale a observación de mediodía local para FWI.

Cambiar provincia o año no requiere cambiar código: la selección opera sobre eventos normalizados.
Canarias requiere aplicar su huso y fuentes regionales sin asumir condiciones peninsulares.
