from .models import IncidentState

ALLOWED_TRANSITIONS: dict[IncidentState, frozenset[IncidentState]] = {
    IncidentState.SIN_EVIDENCIA: frozenset({IncidentState.VIGILANCIA}),
    IncidentState.VIGILANCIA: frozenset(
        {IncidentState.ANOMALIA, IncidentState.DESCARTADO}
    ),
    IncidentState.ANOMALIA: frozenset(
        {
            IncidentState.VIGILANCIA,
            IncidentState.POSIBLE_IGNICION,
            IncidentState.DESCARTADO,
        }
    ),
    IncidentState.POSIBLE_IGNICION: frozenset(
        {
            IncidentState.ANOMALIA,
            IncidentState.PROBABLE_INCENDIO,
            IncidentState.DESCARTADO,
        }
    ),
    IncidentState.PROBABLE_INCENDIO: frozenset(
        {IncidentState.POSIBLE_IGNICION, IncidentState.DESCARTADO}
    ),
    IncidentState.INCENDIO_CONFIRMADO: frozenset(),
    IncidentState.DESCARTADO: frozenset({IncidentState.VIGILANCIA}),
}


def transition_is_allowed(previous: IncidentState, new: IncidentState) -> bool:
    return new == previous or new in ALLOWED_TRANSITIONS[previous]


def require_allowed_transition(previous: IncidentState, new: IncidentState) -> None:
    if not transition_is_allowed(previous, new):
        raise ValueError(f"Transición no permitida: {previous.value} -> {new.value}")


def transition_path(
    previous: IncidentState, recommendation: IncidentState
) -> tuple[IncidentState, ...]:
    """Return the shortest explicit state path without auto-confirmation."""
    if recommendation is IncidentState.INCENDIO_CONFIRMADO:
        raise ValueError("INCENDIO_CONFIRMADO requiere confirmación externa aprobada.")
    if previous == recommendation:
        return ()
    frontier: list[tuple[IncidentState, tuple[IncidentState, ...]]] = [(previous, ())]
    visited = {previous}
    while frontier:
        state, path = frontier.pop(0)
        for candidate in sorted(ALLOWED_TRANSITIONS[state], key=lambda item: item.value):
            if candidate is IncidentState.INCENDIO_CONFIRMADO or candidate in visited:
                continue
            if (
                candidate is IncidentState.DESCARTADO
                and recommendation is not IncidentState.DESCARTADO
            ):
                continue
            next_path = (*path, candidate)
            if candidate == recommendation:
                return next_path
            visited.add(candidate)
            frontier.append((candidate, next_path))
    raise ValueError(
        f"No existe transición segura: {previous.value} -> {recommendation.value}"
    )
