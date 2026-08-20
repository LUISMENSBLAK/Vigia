# Validación geoespacial LIVE — Fase 4B

Fecha de comprobación: 2026-08-20 UTC. Este documento distingue respuesta de servicio, producto
descubierto, descarga validada y artefacto publicado. Un HTTP 200 no implica cobertura científica.

## AOI

La AOI real es la tesela proyectada `[356000, 4501000, 357000, 4502000]` en EPSG:25830, dentro de
la provincia de Ávila. La elección procede de una tesela LiDAR PNOA publicada; no es un límite
administrativo ni una representación de toda Ávila. La configuración incluye España, Castilla y
León, Ávila, municipios asociados y Segovia como segunda provincia de control.

## Fuentes oficiales comprobadas

- IGN OGC API Features: unidades administrativas de comunidad, provincias y municipios. El país
  usa el contorno generalizado GISCO 2024 para evitar una transferencia nacional innecesaria.
- IGN/IDEE WCS MDT: `Elevacion25830_5`, GeoTIFF real, EPSG:25830, 5 m.
- CNIG LiDAR PNOA: catálogo real y tesela `PNOA-2025-CYL-356-4502-H30-NPC01.LAZ`, 5 puntos/m².
  La descarga llegó incompleta en los intentos realizados; validación y publicación `BLOCKED`.
  Tras esos intentos, la configuración de esta ejecución desactiva solo la repetición de la
  transferencia; el materializador nacional mantiene el intento habilitado por defecto.
  El producto descubierto conserva un manifiesto `ERROR` idempotente y sanitizado; no se asignan
  tamaño ni checksum a una descarga que no terminó.
- Copernicus Data Space: OAuth, catálogo Sentinel-2 L2A y Process API sobre una AOI pequeña.
- IGN/IDEE WFS ocupación del suelo: `lcv:LandCoverUnit`, dataset `siose_ar2017`, nomenclatura
  `CODIIGEValue`; el cliente pagina y conserva geometría/provenance.
- EUMETSAT Data Store: colección `EO:EUM:DAT:0682` y productos AFM visibles por catálogo anónimo.
  Las credenciales adjuntas devolvieron `invalid_client`; descarga/netCDF `BLOCKED`.

## URLs de referencia

- MDT: `https://servicios.idee.es/wcs-inspire/mdt`
- SIOSE AR: `https://servicios.idee.es/wfs-inspire/ocupacion-suelo`
- Administraciones IGN: `https://api-features.ign.es/collections/administrativeunit/items`
- LiDAR CNIG: `https://centrodedescargas.cnig.es/CentroDescargas/catalogo.do?Serie=LIDA3`
- GISCO: `https://gisco-services.ec.europa.eu/distribution/v2/countries/`
- EUMETSAT Data Store guide:
  `https://user.eumetsat.int/resources/user-guides/data-store-detailed-guide`
- EUMETSAT AFM:
  `https://user.eumetsat.int/catalogue/EO%3AEUM%3ADAT%3A0682`

## Estados pendientes

Los Advisors de Security y Performance de Supabase permanecen `NO VERIFICADO`: las variables
locales permiten PostgreSQL/Data API, pero no incluyen un access token de gestión del proyecto.
No se infiere su resultado desde SQL.

## Resultado materializado

La ejecución con commit `28313230cdc0713734879d72394e0f12fbace94a` produjo y persistió:

- 6 unidades administrativas: país, comunidad, 2 provincias y 2 municipios;
- 4 COG de terreno de 5 m en EPSG:25830: elevación, pendiente, orientación y ruggedness;
- 3 COG Sentinel-2 de 10 m en EPSG:32630: NDVI, NDMI y NBR;
- 1 producto SIOSE AR 2017 con 2.726 features para la AOI;
- 0 productos LiDAR, por descarga oficial incompleta.

La escena Sentinel-2 fue
`S2B_MSIL2A_20260818T110619_N0512_R137_T30TUL_20260818T132515.SAFE`, adquirida el
2026-08-18 11:19:49.772 UTC. La máscara SCL/dataMask dejó 100 % de píxeles válidos en esta muestra;
esto no se extrapola fuera de la AOI.

El área geodésica calculada es 1,000293 km². Dentro de ella: terreno válido 100 %, vegetación válida
100 %, unión geométrica SIOSE 99,999266 % y LiDAR publicado 0 %. Los porcentajes son cobertura de
datos de esta AOI, no precisión científica.

Los siete COG pequeños son tiled, DEFLATE, nodata `-9999`, con CRS/resolución verificados. Al medir
100×100 o 200×200 píxeles no requieren pirámides para cumplir la validación COG mínima aplicada.

## Persistencia, API y regresión

PostGIS remoto devolvió versión 3.3. La auditoría encontró 35 tablas internas, RLS habilitado y
forzado en 35/35, 18 índices GiST, 41 foreign keys, 383 checks y cero grants de escritura para
`PUBLIC`, `anon` o `authenticated`. Hay 8 productos vigentes y 4 versiones previas invalidadas con
su relación de supersesión.

`/api/geospatial/layers`, `/coverage`, `/context` y `/tiles` respondieron HTTP 200. Una consulta al
centroide devolvió administración oficial, valores reales de terreno, NDVI/NDMI/NBR y clase SIOSE;
LiDAR devolvió `NO DISPONIBLE`. La tesela retornó PNG desde el COG, no el GeoTIFF completo.

Smoke LIVE: FIRMS autenticó y parseó correctamente una AOI pequeña con cero observaciones (cero no
es un fallo); AEMET autenticó y parseó 10.559 observaciones del endpoint convencional. Fusion
procesó 2.090 observaciones persistidas, obtuvo 3 candidatos y creó 3 incidentes en `VIGILANCIA`;
ninguno fue `INCENDIO_CONFIRMADO`.

EUMETSAT queda `BLOCKED`: el catálogo anónimo mostró 17 productos AFM en tres horas y el más reciente
comenzó a las 09:10 UTC, pero OAuth devolvió `invalid_client`. No hubo descarga ni validación netCDF.
