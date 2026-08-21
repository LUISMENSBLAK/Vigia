# Límites actuales de la validación científica

## Cobertura

El dataset evaluable v1 no es nacional: representa Castilla y León. MITECO/EGIF se catalogó como
fuente nacional, pero el paquete RDF 1983–2015 inspeccionado no enlaza timestamps de incendio a sus
registros y no puede alimentar Replay temporal sin otra referencia compatible. EFFIS/Copernicus
es evidencia externa útil, no verdad absoluta.

La clasificación `HIGH` describe el cumplimiento del contrato de selección v1; no convierte una
coordenada oficial aproximada en origen exacto ni elimina errores de registro.

## Potencia y sesgo

Solo un evento DEVELOPMENT dispone de Replay materializado. No hay potencia para estimar recall,
latencia, localización, variación regional, estacional, por tamaño, sensor, terreno o meteorología.
La cobertura de Replay debe ampliarse sin seleccionar casos por el resultado del motor.

El dataset solo contiene positivos. No se llaman `TRUE_NEGATIVE` a periodos sin registro. Precision,
F1 y falsas alertas exigen ventanas área-tiempo con fuentes oficiales, exclusiones y cobertura de
sensor defendibles. Hasta entonces permanecen `NO DISPONIBLE`.

## Tiempo y geometría

El histórico FIRMS permite tiempo de observación, pero no reconstruye de forma defendible cuándo
el producto estuvo operacionalmente disponible para VIGÍA. Esa latencia no se estima. No hay una
muestra de perímetros temporalmente compatibles para IoU, Hausdorff o error de área.

## Scores y TEST

`evidence_strength` y el Risk Baseline no son probabilidades calibradas. PR-AUC, Brier, ECE y
curvas de calibración no se calculan sobre esos valores como si lo fueran.

TEST contiene 1.172 referencias, permanece congelado y no fue leído por el ValidationRun. Abrirlo
requiere una configuración candidata congelada y un registro de auditoría inmutable. Su mera
existencia no valida el modelo.

## Claims permitidos

El run demuestra que el pipeline dataset → split → Replay → matching → métricas → persistencia es
reproducible e idempotente para la muestra materializada. No demuestra precisión nacional,
recall operativo, baja tasa de falsas alertas, calibración, latencia ni el objetivo de investigación
99,9 %. Ninguna salida habilita `INCENDIO_CONFIRMADO` automático.
