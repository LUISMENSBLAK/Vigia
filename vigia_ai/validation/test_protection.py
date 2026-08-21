from __future__ import annotations

from datetime import datetime

from vigia_ai.replay.models import canonical_hash


def authorize_test_access(
    *,
    split_hash: str,
    candidate_configuration_hash: str,
    candidate_frozen: bool,
    reason: str,
    requested_at: datetime,
    actor: str,
) -> str:
    if not candidate_frozen:
        raise PermissionError("TEST_SET_FROZEN: la configuración candidata no está congelada")
    if not reason.strip() or not actor.strip():
        raise ValueError("El acceso TEST necesita actor y motivo auditables")
    if requested_at.tzinfo is None:
        raise ValueError("requested_at requiere zona horaria")
    return canonical_hash(
        {
            "split_hash": split_hash,
            "candidate_configuration_hash": candidate_configuration_hash,
            "reason": reason,
            "requested_at": requested_at,
            "actor": actor,
        }
    )
