from __future__ import annotations

from typing import Any, Callable

from .._keys import snake_aliases
from . import _events
from ._bridge import Subscription


class _AppStateMeta(type):
    @property
    def currentState(cls) -> str:
        return cls._state


@snake_aliases
class AppState(metaclass=_AppStateMeta):
    """`AppState.currentState` is "active" or "background"; `change` listeners get the new state."""
    _state = "active"

    @staticmethod
    def addEventListener(event: str, fn: Callable[[str], Any]) -> Subscription:
        if event != "change":
            raise ValueError("AppState.addEventListener: only 'change', got %r" % (event,))
        return Subscription(_events.on("app_state", lambda p: fn(_state_of(p))))


def _state_of(payload: Any) -> str:
    return str((payload or {}).get("state", "active")) if isinstance(payload, dict) else str(payload)


def _track(payload: Any) -> None:
    AppState._state = _state_of(payload)


_events.on("app_state", _track)
