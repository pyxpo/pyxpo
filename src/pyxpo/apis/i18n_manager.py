"""Layout direction (RN `I18nManager`).

Right-to-left mirrors the whole layout: a row starts at the right, `left`/`margin_left`/`padding_left` mean the
right side, and text aligns right. The engine lays out left to right and mirrors each frame inside its parent, so
styles stay written for LTR.

As in Expo, an app is left to right until it opts in: `allowRTL(True)` follows the device language,
`forceRTL(True)` turns RTL on whatever the device says. Both apply at once (no restart needed).
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List

from . import _bridge, _env

_state: Dict[str, Any] = {"allow": False, "force": False, "swap": True, "sent": False}
_listeners: List[Callable[[bool], None]] = []


def _device_rtl() -> bool:
    return bool(_env.current.get().get("rtl"))


def _sync() -> None:
    rtl = bool(_state["force"] or (_state["allow"] and _device_rtl()))
    changed = rtl != I18nManager.isRTL
    I18nManager.isRTL = rtl
    if rtl != _state["sent"] and _bridge.get_app() is not None:
        _bridge.call("I18nManager", "set_rtl", rtl)
        _state["sent"] = rtl
    if changed:
        for fn in list(_listeners):
            fn(rtl)


def on_app(app: Any) -> None:
    """A new App (native starts left to right): sends the direction before the first frame."""
    _state["sent"] = False
    _sync()
    app.env.subscribe(_sync)  # the device language can change while the app runs


class I18nManager:
    """Layout direction flags. `isRTL` is the direction in use."""
    isRTL = False
    doLeftAndRightSwapInRTL = True

    @staticmethod
    def allowRTL(allow: bool) -> None:
        """Follow the device language's direction (off by default)."""
        _state["allow"] = bool(allow)
        _sync()

    @staticmethod
    def forceRTL(force: bool) -> None:
        """Right to left whatever the device language is."""
        _state["force"] = bool(force)
        _sync()

    @staticmethod
    def swapLeftAndRightInRTL(flip: bool) -> None:
        # pyxpo always swaps: left/right styles mean start/end. Kept for RN compatibility.
        _state["swap"] = bool(flip)

    @staticmethod
    def getConstants() -> Dict[str, Any]:
        return {"isRTL": I18nManager.isRTL, "doLeftAndRightSwapInRTL": True,
                "localeIdentifier": _env.current.get().get("locale") or "en_US"}

    @staticmethod
    def addListener(fn: Callable[[bool], None]) -> "_bridge.Subscription":
        """Called with the new `isRTL` when the direction changes."""
        _listeners.append(fn)
        return _bridge.Subscription(lambda: _listeners.remove(fn) if fn in _listeners else None)
