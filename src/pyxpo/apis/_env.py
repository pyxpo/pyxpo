"""Device environment: window size, density, color scheme, insets, keyboard.

Native sends a full snapshot at startup (`hello` handshake) and an `env` event on every change.
All sizes are dp/pt.
"""
from __future__ import annotations

import copy
from typing import Any, Callable, Dict, List, Optional

DEFAULT_ENV: Dict[str, Any] = {
    "os": "desktop",
    "window": {"width": 360.0, "height": 640.0},
    "screen": {"width": 360.0, "height": 640.0},
    "scale": 1.0,
    "font_scale": 1.0,
    "color_scheme": "light",
    "insets": {"top": 0.0, "right": 0.0, "bottom": 0.0, "left": 0.0},
    "keyboard": {"visible": False, "height": 0.0},
    "initial_url": None,  # deep link the app was launched with
}


def _merge(base: Dict[str, Any], upd: Dict[str, Any]) -> Dict[str, Any]:
    for k, v in upd.items():
        if k not in base:
            continue  # ignore unknown keys: forward compatible with newer native
        if isinstance(base[k], dict) and isinstance(v, dict):
            for kk, vv in v.items():
                if kk in base[k]:
                    base[k][kk] = vv
        else:
            base[k] = v
    return base


class Env:
    def __init__(self, snapshot: Optional[Dict[str, Any]] = None) -> None:
        self._data: Dict[str, Any] = copy.deepcopy(DEFAULT_ENV)
        self._listeners: List[Callable[[], None]] = []
        if snapshot:
            _merge(self._data, snapshot)

    def get(self) -> Dict[str, Any]:
        return copy.deepcopy(self._data)

    def update(self, upd: Dict[str, Any]) -> bool:
        before = copy.deepcopy(self._data)
        _merge(self._data, upd)
        if before == self._data:
            return False
        for fn in list(self._listeners):
            fn()
        return True

    def subscribe(self, fn: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(fn)

        def off() -> None:
            if fn in self._listeners:
                self._listeners.remove(fn)

        return off


current = Env()  # replaced by App on creation; the statics (Dimensions, Platform, ...) read it
_boot = current


def set_current(env: Env) -> None:
    """Points the statics at the App's env. Listeners added before any App existed move over."""
    global current
    if current is _boot and env is not _boot:
        env._listeners.extend(fn for fn in _boot._listeners if fn not in env._listeners)
        _boot._listeners.clear()
    current = env
