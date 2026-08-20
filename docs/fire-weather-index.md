# Canadian Fire Weather Index 1987

## Implementación

VIGÍA implementa FFMC, DMC, DC, ISI, BUI y FWI conforme al código actualizado y probado
contra el FORTRAN original por Natural Resources Canada / Canadian Forest Service:

- Wang, Y.; Anderson, K.R.; Suddaby, R.M. (2015), *Updated source code for calculating
  fire danger indices in the Canadian Forest Fire Weather Index System*, NOR-X-424.
  https://publications.gc.ca/collections/collection_2016/rncan-nrcan/Fo133-1-424-eng.pdf
- Van Wagner, C.E.; Pickett, T.L. (1985), Forestry Technical Report 33.

La prueba de regresión reproduce la tabla 7 de NOR-X-424 con tolerancia de redondeo de
0,06 para los seis componentes en una secuencia de cinco días.

## Entradas y estado

El sistema diario clásico requiere temperatura (°C), humedad relativa (%), viento
(km/h) y precipitación acumulada de 24 h (mm) al mediodía local estándar. FFMC, DMC y DC
son estados encadenados: el valor válido del día anterior es obligatorio.

Los valores iniciales publicados (85, 6, 15) solo son admisibles como inicio explícito de
temporada bajo un protocolo documentado. VIGÍA no los introduce de forma silenciosa en
una fecha aislada. Sin historia suficiente, devuelve `INSUFFICIENT_DATA`.

## AEMET e interpolación

Las observaciones AEMET siguen siendo `OBSERVADO`. IDW p=2 informa estaciones,
distancias, edad máxima y soporte efectivo; no crea meteorología a 10 m. Los productos
horarios municipales son `PRONOSTICADO` y alcanzan hasta 48 horas según la especificación
oficial: https://opendata.aemet.es/AEMET_OpenData_specification.json

AEMET publica por separado precipitación horaria y probabilidad por intervalos. VIGÍA no
transforma probabilidad en milímetros. Un registro horario aislado todavía no permite
calcular FWI: requiere acumulación de 24 h, hora diaria normalizada y estado previo.

## Límites

FWI caracteriza peligro meteorológico relativo; no es probabilidad de incendio, no
incluye igniciones, supresión, combustible validado ni propagación. Su traslado a España
requiere validación regional. EFFIS es benchmark externo, no verdad terreno.
