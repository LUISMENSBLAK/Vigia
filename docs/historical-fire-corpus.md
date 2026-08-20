# Corpus histórico nacional de incendios

## Estado y alcance

Fase 6 crea la arquitectura nacional y un piloto reproducible, no un corpus nacional completo. Un
registro oficial es una **referencia histórica**, no una verdad infalible. Las revisiones de un
mismo parte se conservan por separado y se resuelven hacia un evento canónico estable. No se
inventan hora, origen, perímetro ni estado final cuando la fuente no los publica.

## Fuentes oficiales evaluadas

- [MITECO — Estadísticas de incendios forestales](https://www.miteco.gob.es/gl/biodiversidad/temas/incendios-forestales/estadisticas-datos.html): EGIF existe desde 1968, contiene más de 150 campos y ofrece consulta consolidada, resúmenes y descarga XML. La metodología oficial aclara que los microdatos no se entregan directamente como fichero general; por eso Fase 6 no afirma haber materializado EGIF nacional.
- [Catálogo nacional de EGIF](https://datos.gob.es/en/catalogo/e05068001-estadistica-general-de-incendios-forestales): referencia reproducible del conjunto estatal.
- [Junta de Castilla y León — Incendios forestales](https://datosabiertos.jcyl.es/web/jcyl/set/es/medio-ambiente/incendios_forestales/1284333417830): fuente regional pública elegida para el piloto por incluir posiciones, fechas/horas, municipio, provincia, superficie reportada y versiones sucesivas.
- [Copernicus Climate Data Store — Burned Area](https://cds.climate.copernicus.eu/datasets/satellite-fire-burned-area?tab=overview): FireCCI51 (250 m, 2001–2019) y C3S/OLCI (300 m, 2017–presente) son candidatos para cobertura quemada. No se confunden con perímetros oficiales ni se han materializado en el piloto inicial.
- [EFFIS user guide](https://data.effis.emergency.copernicus.eu/effis/applications/effis.viewer/userguide.pdf): los datos históricos o perímetros pueden requerir solicitud. Permanecen `NO VERIFICADO` hasta disponer del acceso y licencia aplicables.

## Modelo

`historical_fires` contiene la identidad canónica. `historical_fire_references` conserva cada
versión, registro original, checksum, recuperación, fuente y calidad. Los timestamps viven en
`historical_fire_timestamps` con semántica y precisión (`DATE_ONLY`, `HOUR`, `MINUTE`, `EXACT`,
`UNKNOWN`). `historical_fire_perimeters` conserva geometría, fecha de referencia, CRS, resolución,
método y provenance; el piloto inicial no inventa ninguno si la fuente no lo ofrece.

La clave de evento piloto se deriva de proveedor, fecha/hora publicada, municipio y posición. No
utiliza la salida de VIGÍA. Una corrección del parte produce una nueva referencia con hash propio y
se agrega al mismo evento cuando mantiene esa identidad. Toda deduplicación es determinista.

## Limitaciones y licencias

La cobertura piloto es Castilla y León, años publicados por la fuente en la fecha de descarga. No
representa todavía España completa. La licencia concreta del endpoint regional permanece
`NO VERIFICADO` en el catálogo interno hasta revisión jurídica; el código almacena URI de fuente y
no redistribuye el snapshot bruto en Git. Las referencias pueden tener errores o actualizarse.
