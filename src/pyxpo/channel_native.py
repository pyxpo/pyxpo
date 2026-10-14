from __future__ import annotations

from typing import Callable

from .channel import Channel


class NativeChannel(Channel):
    """Channel backed by the `_pyxpo_bridge` C module (only importable inside a Pyxpo mobile shell)."""

    def __init__(self) -> None:
        import _pyxpo_bridge  # type: ignore

        self._bridge = _pyxpo_bridge

    def post(self, payload: str) -> None:
        self._bridge.post(payload)

    def set_event_handler(self, fn: Callable[[str], None]) -> None:
        # Native calls this on its UI thread under the GIL; App.dispatch_event hops to the asyncio loop.
        self._bridge.set_event_handler(fn)
