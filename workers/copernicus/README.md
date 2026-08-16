# Copernicus worker

El cliente OAuth2 Client Credentials cachea el access token y lo renueva con margen de 60 segundos.
Catalog limita resultados y obliga a bbox y ventana temporal. El builder Sentinel-2 solicita un AOI
y salida acotada para NDVI, NDMI y NBR; no descarga escenas completas.

Sentinel-1 GRD y Sentinel-3 SLSTR están registrados con sus identificadores oficiales. Su ejecución,
persistencia y cualquier interpretación térmica permanecen `EN PREPARACIÓN` hasta validar una
respuesta real con credenciales.
