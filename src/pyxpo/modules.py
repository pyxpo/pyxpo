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


class Toast:
    @staticmethod
    def show(message: str, long: bool = False) -> None:
        """Shows the platform toast (android.widget.Toast)."""
        call("Toast", "show", str(message), bool(long))


def spawn(coro: Any) -> None:
    """Runs a coroutine on the app loop from a sync callback (errors go to the app's error handler)."""
    loop = getattr(_app, "loop", None)
    if loop is None:
        coro.close()
        return

    async def run() -> None:
        try:
            await coro
        except Exception as e:  # noqa: BLE001
            if getattr(_app, "on_error", None):
                _app.on_error(e)
    loop.create_task(run())


class Picker:
    """Native pickers: system date / time dialogs and choice lists. Each returns None when cancelled."""

    @staticmethod
    async def date(year: int, month: int, day: int, minimum: Optional[tuple] = None,
                   maximum: Optional[tuple] = None, title: str = "") -> Optional[tuple]:
        v = await call("Picker", "date", int(year), int(month), int(day), list(minimum) if minimum else None,
                       list(maximum) if maximum else None, str(title), reply=True)
        return tuple(v) if v else None

    @staticmethod
    async def time(hour: int, minute: int, is_24h: bool = False, title: str = "") -> Optional[tuple]:
        v = await call("Picker", "time", int(hour), int(minute), bool(is_24h), str(title), reply=True)
        return tuple(v) if v else None

    @staticmethod
    async def choose(labels: list, selected: int = -1, title: str = "") -> Optional[int]:
        v = await call("Picker", "choose", [str(x) for x in labels], int(selected), str(title), reply=True)
        return None if v is None or int(v) < 0 else int(v)

    @staticmethod
    async def choose_many(labels: list, selected: list, title: str = "") -> Optional[list]:
        v = await call("Picker", "choose_many", [str(x) for x in labels], [int(i) for i in selected], str(title),
                       reply=True)
        return None if v is None else [int(i) for i in v]
