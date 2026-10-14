from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..apis import _bridge
from ..component import component
from ..hooks import use_effect

_stack: List[Dict[str, Any]] = []
_applied: Dict[str, Any] = {}
_GLYPH = {"dark-content": "dark", "light-content": "light", "default": "dark"}


def _apply() -> None:
    """The newest mounted StatusBar wins, per prop."""
    merged: Dict[str, Any] = {}
    for e in _stack:
        merged.update({k: v for k, v in e.items() if v is not None})
    for key, method, conv in (("barStyle", "set_style", lambda v: _GLYPH.get(v, "dark")),
                              ("hidden", "set_hidden", bool),
                              ("backgroundColor", "set_background", None),
                              ("translucent", "set_translucent", bool)):
        if key in merged and merged[key] != _applied.get(key):
            _applied[key] = merged[key]
            try:
                if key == "backgroundColor":
                    from ..style import processColor
                    _bridge.call("StatusBar", method, processColor(merged[key]))
                else:
                    _bridge.call("StatusBar", method, conv(merged[key]))
            except RuntimeError:
                pass  # no running app (tests / desktop)


@component
def StatusBar(bar_style: Optional[str] = None, hidden: Optional[bool] = None, background_color: Any = None,
              translucent: Optional[bool] = None, animated: bool = False, **props: Any):
    """Declarative status bar; the newest mounted one wins. `barStyle`: "default" | "light-content" |
    "dark-content". `backgroundColor` / `translucent` are Android only."""
    entry = {"barStyle": bar_style, "hidden": hidden, "backgroundColor": background_color, "translucent": translucent}

    def mount():
        _stack.append(entry)
        _apply()

        def unmount() -> None:
            if entry in _stack:
                _stack.remove(entry)
            _apply()
        return unmount

    use_effect(mount, [bar_style, hidden, background_color, translucent])
    return None


_imperative: Dict[str, Any] = {}
_stack.append(_imperative)  # lowest layer: setBarStyle() & co. until a mounted <StatusBar> overrides


def _setter(key: str):
    def setter(value: Any, animated: bool = False) -> None:
        _imperative[key] = value
        _apply()
    return setter


StatusBar.set_bar_style = StatusBar.setBarStyle = _setter("barStyle")
StatusBar.set_hidden = StatusBar.setHidden = _setter("hidden")
StatusBar.set_background_color = StatusBar.setBackgroundColor = _setter("backgroundColor")
StatusBar.set_translucent = StatusBar.setTranslucent = _setter("translucent")
