from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class ReplayClock:
    def __init__(self, *, start: datetime, end: datetime, step: timedelta) -> None:
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("ReplayClock requiere timestamps con zona horaria")
        if end < start or step <= timedelta(0):
            raise ValueError("Ventana o paso de replay inválido")
        self._start = start.astimezone(UTC)
        self._end = end.astimezone(UTC)
        self._step = step
        self._current = self._start

    def now(self) -> datetime:
        return self._current

    @property
    def step(self) -> timedelta:
        return self._step

    def seek(self, target: datetime) -> datetime:
        if target.tzinfo is None:
            raise ValueError("El corte de replay requiere zona horaria")
        normalized = target.astimezone(UTC)
        if not self._start <= normalized <= self._end:
            raise ValueError("El corte está fuera de la ventana del replay")
        self._current = normalized
        return self._current

    def advance(self) -> datetime | None:
        target = self._current + self._step
        if target > self._end:
            return None
        self._current = target
        return self._current

    def timeline(self) -> tuple[datetime, ...]:
        output: list[datetime] = []
        current = self._start
        while current <= self._end:
            output.append(current)
            current += self._step
        return tuple(output)
