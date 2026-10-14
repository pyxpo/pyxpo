from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback
from typing import Any, Callable, List, Optional

from .channel import Channel, LocalChannel
from .component import Component
from .element import Element
from .ops import to_json
from .reconciler import Fiber, Reconciler


class App:
    """Owns a reconciler and a channel. Batches setState into one flush per loop tick."""

    def __init__(self, root: Any, channel: Channel, loop: Optional[asyncio.AbstractEventLoop] = None,
                 **props: Any) -> None:
        self.channel = channel
        self.loop = loop
        self.dirty: List[Fiber] = []
        self.flushing = False
        self._flush_requested = False
        self.on_error: Callable[[BaseException], None] = lambda e: traceback.print_exception(
            type(e), e, e.__traceback__, file=sys.stderr)
        self.rec = Reconciler(self._schedule)
        self.rec.loop = loop
        if isinstance(root, Element):
            self._root_element = root
        elif isinstance(root, Component):
            self._root_element = root(**props)
        else:
            self._root_element = Component(root)(**props)
        channel.set_event_handler(self.dispatch_event)

    def start(self) -> None:
        self.flushing = True
        try:
            self.rec.render(self._root_element)
            self._send(self.rec.take_ops())
            self.rec.run_effects()
        finally:
            self.flushing = False
        self.flush()

    def flush(self) -> None:
        if self.flushing:
            return
        self.flushing = True
        try:
            for _ in range(100):
                if not self.dirty:
                    break
                batch = sorted(self.dirty, key=lambda f: f.depth)
                self.dirty = []
                for f in batch:
                    self.rec.update(f)
                self._send(self.rec.take_ops())
                self.rec.run_effects()
            else:
                raise RuntimeError("too many consecutive updates (state set on every render?)")
        finally:
            self.flushing = False

    def dispatch_event(self, payload: str) -> None:
        if self.loop is not None:
            self.loop.call_soon_threadsafe(self._handle_event, payload)
        else:
            self._handle_event(payload)

    # -- internals -----------------------------------------------------
    def _handle_event(self, payload: str) -> None:
        msg = json.loads(payload)
        try:
            self.rec.dispatch(msg["id"], msg["event"], msg.get("payload"))
        except Exception as e:  # noqa: BLE001
            self.on_error(e)
        self._request_flush()

    def _schedule(self, fiber: Fiber) -> None:
        if fiber not in self.dirty:
            self.dirty.append(fiber)
        if not self.flushing:
            self._request_flush()

    def _request_flush(self) -> None:
        if self.loop is None:
            self._safe_flush()
        elif not self._flush_requested:
            self._flush_requested = True
            self.loop.call_soon_threadsafe(self._run_scheduled_flush)

    def _run_scheduled_flush(self) -> None:
        self._flush_requested = False
        self._safe_flush()

    def _safe_flush(self) -> None:
        try:
            self.flush()
        except Exception as e:  # noqa: BLE001
            if self.loop is None:
                raise
            self.on_error(e)

    def _send(self, ops: list) -> None:
        if ops:
            self.channel.post(to_json(ops))


def create_app(root: Any, channel: Channel, **props: Any) -> App:
    """Mount without an event loop (synchronous flushes). Used by tests and tooling."""
    app = App(root, channel, None, **props)
    app.start()
    return app


def run_app(root: Any, channel: Optional[Channel] = None, **props: Any) -> None:
    """Run the app on the current platform. Desktop target uses the console renderer."""
    target = os.environ.get("PYXPO_TARGET", "desktop")
    if channel is None and target != "desktop":
        from .channel_native import NativeChannel
        channel = NativeChannel()

    async def main() -> None:
        loop = asyncio.get_running_loop()
        renderer = None
        ch = channel
        if ch is None:
            from .renderers.console import ConsoleRenderer
            ch = LocalChannel()
            renderer = ConsoleRenderer(ch)
        app = App(root, ch, loop, **props)
        app.start()
        if renderer is not None:
            await renderer.run()
        else:
            await asyncio.Event().wait()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
