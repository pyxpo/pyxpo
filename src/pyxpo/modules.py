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
