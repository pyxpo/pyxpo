"""Tiny emitter for system events native pushes without a view id (`url`, `app_state`)."""
from __future__ import annotations

import traceback
from typing import Any, Callable, Dict, List

_listeners: Dict[str, List[Callable[[Any], Any]]] = {}


def on(name: str, fn: Callable[[Any], Any]) -> Callable[[], None]:
    _listeners.setdefault(name, []).append(fn)

    def off() -> None:
        lst = _listeners.get(name, [])
        if fn in lst:
            lst.remove(fn)

    return off


def emit(name: str, payload: Any) -> None:
    """Calls every listener; one that raises is reported and does not keep the event from the others."""
    for fn in list(_listeners.get(name, ())):
        try:
            fn(payload)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
