"""Thin wrappers over native modules (Keyboard, Clipboard, Linking, Vibration, Alert).

Each wrapper sends a `call` op. Methods that return a value are awaitable (`await Clipboard.get_string()`).
On desktop/mock renderers calls are recorded and do nothing.
"""
from __future__ import annotations

from typing import Any, Optional

_app: Optional[Any] = None


def set_app(app: Any) -> None:
    global _app
    _app = app


def call(module: str, method: str, *args: Any, reply: bool = False) -> Any:
    if _app is None:
        raise RuntimeError("no running pyxpo app")
    return _app.call(module, method, *args, reply=reply)


class StatusBar:
    """System status bar. `style` is the glyph colour: "dark" (for light backgrounds) or "light"."""
    _style = None

    @classmethod
    def set_style(cls, style: str) -> None:
        if style != cls._style and _app is not None:
            cls._style = style
            call("StatusBar", "set_style", style)


class Back:
    """Android hardware back. Navigators register a handler; the newest handler that returns True consumes it."""
    _handlers: list = []
    _enabled = False

    @classmethod
    def add(cls, fn: Any) -> Any:
        cls._handlers.append(fn)
        cls._sync()

        def remove() -> None:
            if fn in cls._handlers:
                cls._handlers.remove(fn)
            cls._sync()
        return remove

    @classmethod
    def _sync(cls) -> None:
        on = bool(cls._handlers)
        if on != cls._enabled and _app is not None:
            cls._enabled = on
            call("Back", "set_enabled", on)

    @classmethod
    def handle(cls) -> None:
        for fn in reversed(list(cls._handlers)):
            if fn():
                return
        call("Back", "exit")  # nobody consumed it: leave the app


class Keyboard:
    @staticmethod
    def dismiss() -> None:
        call("Keyboard", "dismiss")


class Clipboard:
    @staticmethod
    def set_string(text: str) -> None:
        call("Clipboard", "set_string", str(text))

    @staticmethod
    async def get_string() -> str:
        return (await call("Clipboard", "get_string", reply=True)) or ""


class Linking:
    @staticmethod
    def open_url(url: str) -> None:
        call("Linking", "open_url", str(url))


class Vibration:
    @staticmethod
    def vibrate(ms: int = 50) -> None:
        call("Vibration", "vibrate", int(ms))


class Alert:
    @staticmethod
    async def alert(title: str, message: str = "", buttons: Optional[list] = None) -> int:
        """Shows a native dialog. Returns the index of the pressed button."""
        labels = [str(b) for b in (buttons or ["OK"])]
        v = await call("Alert", "alert", str(title), str(message), labels, reply=True)
        return int(v or 0)
