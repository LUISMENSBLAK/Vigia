# Confidence Engine

Estado: `research`. `contracts.py` define evidencia versionable, grupo de independencia, edad,
resolución, persistencia y hashes, además de las puertas de consistencia espacial/temporal,
meteorología, vegetación y contradicciones.

El contrato de research obliga `calibrated_probability = null`. No existe todavía una función que
combine evidencias: una media de confidence de sensores sería científicamente inválida. Solo una
versión calibrada, validada por región/tiempo y acompañada de model card podrá producir una
probabilidad futura.
