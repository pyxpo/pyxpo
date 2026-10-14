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


class _Sub:
    def __init__(self, off: Any) -> None:
        self._off = off

    def remove(self) -> None:
        self._off()


class BackHandler:
    """RN BackHandler: `add_event_listener("hardwareBackPress", fn)`; the newest listener returning True consumes it."""

    @staticmethod
    def add_event_listener(event: str, fn: Any) -> _Sub:
        if event not in ("hardwareBackPress", "hardware_back_press"):
            raise ValueError("BackHandler: only 'hardwareBackPress', got %r" % (event,))
        return _Sub(Back.add(fn))

    addEventListener = add_event_listener

    @staticmethod
    def exit_app() -> None:
        call("Back", "exit")

    exitApp = exit_app


class Keyboard:
    @staticmethod
    def dismiss() -> None:
        call("Keyboard", "dismiss")

    @staticmethod
    def add_listener(event: str, fn: Any) -> _Sub:
        """`keyboardDidShow` / `keyboardDidHide`; `fn({"height"})` fires when the keyboard visibility flips."""
        if event not in ("keyboardDidShow", "keyboardDidHide"):
            raise ValueError("Keyboard.add_listener: 'keyboardDidShow' or 'keyboardDidHide', got %r" % (event,))
        from .env import current
        want = event == "keyboardDidShow"
        last = [bool(current._data["keyboard"]["visible"])]

        def on_env() -> None:
            kb = current._data["keyboard"]
            vis = bool(kb["visible"])
            if vis != last[0]:
                last[0] = vis
                if vis == want:
                    fn({"height": kb["height"]})

        return _Sub(current.subscribe(on_env))

    addListener = add_listener


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

    openURL = open_url


class Vibration:
    @staticmethod
    def vibrate(ms: int = 50) -> None:
        call("Vibration", "vibrate", int(ms))


class Alert:
    @staticmethod
    def alert(title: str, message: str = "", buttons: Optional[list] = None) -> Any:
        """Shows a native dialog and returns an awaitable that resolves to the pressed button index.

        `buttons`: labels, or RN dicts `{"text", "onPress"/"on_press", "style"}`. Button callbacks run when the
        dialog closes, so it works with or without `await`.
        """
        items = list(buttons or ["OK"])
        labels = [str(b.get("text", "OK")) if isinstance(b, dict) else str(b) for b in items]

        async def run() -> int:
            v = int(await call("Alert", "alert", str(title), str(message), labels, reply=True) or 0)
            b = items[v] if 0 <= v < len(items) else None
            cb = (b.get("on_press") or b.get("onPress")) if isinstance(b, dict) else None
            if cb is not None:
                r = cb()
                if hasattr(r, "__await__"):
                    await r
            return v

        loop = getattr(_app, "loop", None)
        if loop is None:
            return run()  # no loop yet (tests / desktop): caller awaits it
        task = loop.create_task(run())
        task.add_done_callback(_alert_done)
        return task


class Toast:
    @staticmethod
    def show(message: str, long: bool = False) -> None:
        """Shows the platform toast (android.widget.Toast)."""
        call("Toast", "show", str(message), bool(long))


def _alert_done(task: Any) -> None:
    if not task.cancelled() and task.exception() is not None and getattr(_app, "on_error", None):
        _app.on_error(task.exception())


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
