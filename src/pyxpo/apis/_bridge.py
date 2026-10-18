"""Link between the JS-less API classes and the running App: native `call` ops and loop access."""
from __future__ import annotations

from typing import Any, Optional

_app: Optional[Any] = None


def set_app(app: Any) -> None:
    global _app
    _app = app


def get_app() -> Optional[Any]:
    return _app


def call(module: str, method: str, *args: Any, reply: bool = False) -> Any:
    if _app is None:
        raise RuntimeError("no running pyxpo app")
    return _app.call(module, method, *args, reply=reply)


def report(exc: BaseException) -> None:
    """Sends an error from a background task to the app error handler (stderr when the app has none)."""
    handler = getattr(_app, "on_error", None)
    if handler:
        handler(exc)
    else:
        import traceback
        traceback.print_exception(type(exc), exc, exc.__traceback__)


def spawn(coro: Any) -> Any:
    """Runs a coroutine on the app loop from a sync callback. Errors go to `report`.
    An app mounted without a loop (tests, tooling) uses the running loop when there is one."""
    loop = getattr(_app, "loop", None)
    if loop is None:
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            coro.close()
            return None

    async def run() -> None:
        try:
            await coro
        except Exception as e:  # noqa: BLE001
            report(e)

    return loop.create_task(run())


class Subscription:
    """What `addEventListener` returns (RN `EmitterSubscription`)."""

    def __init__(self, off: Any) -> None:
        self._off = off

    def remove(self) -> None:
        self._off()
