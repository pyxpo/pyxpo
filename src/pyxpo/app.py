from __future__ import annotations

import asyncio
import contextlib
import gc
import json
import os
import sys
import traceback
from typing import Any, Callable, Dict, List, Optional

from . import env as env_mod
from . import modules as modules_mod
from .animated import runtime as anim_runtime
from .channel import Channel, LocalChannel
from .component import Component, component
from .element import Element
from .hooks import reset_deps
from .ops import Create, Delete, Insert, Remove, to_json
from .reconciler import Fiber, Reconciler


_ERROR_ID = 2 ** 31 - 1  # reserved native id for the dev error overlay


class _HotState:
    """Set by the dev reloader while it re-executes app modules."""
    reloading = False
    captured: Optional[tuple] = None
    entry: Optional[str] = None


_hot = _HotState()


@contextlib.contextmanager
def _gc_paused():
    """Pause the cyclic GC while a commit allocates thousands of short-lived objects (elements, wire dicts):
    a big mount otherwise triggers several full collections mid-render. Garbage is collected right after."""
    was = gc.isenabled()
    gc.disable()
    try:
        yield
    finally:
        if was:
            gc.enable()


def _walk(fiber: Fiber):
    yield fiber
    for c in fiber.children:
        yield from _walk(c)


class App:
    """Owns a reconciler and a channel. Batches setState into one flush per loop tick."""

    def __init__(self, root: Any, channel: Channel, loop: Optional[asyncio.AbstractEventLoop] = None,
                 **props: Any) -> None:
        self.channel = channel
        self.loop = loop
        self.dirty: List[Fiber] = []
        self._dirty_set: set = set()
        self.flushing = False
        self._flush_requested = False
        self.on_error: Callable[[BaseException], None] = lambda e: traceback.print_exception(
            type(e), e, e.__traceback__, file=sys.stderr)
        self.rec = Reconciler(self._schedule)
        self.rec.loop = loop
        self.env = self.rec.env
        env_mod.set_current(self.env)
        if os.environ.get("PYXPO_ENV"):  # native snapshot, so the first render already has the real window size
            try:
                self.env.update(json.loads(os.environ["PYXPO_ENV"]))
            except ValueError:
                pass
        self.broken = False
        self._call_id = 0
        self._pending: Dict[int, Any] = {}
        modules_mod.set_app(self)
        anim_runtime.set_app(self)
        self._committed: Dict[int, int] = {}  # native node id -> parent id (0 = detached)
        self._error_shown = False
        self.set_root(root, **props)
        channel.set_event_handler(self.dispatch_event)

    def set_root(self, root: Any, **props: Any) -> None:
        if isinstance(root, Element):
            self._root_element = root
        elif isinstance(root, Component):
            self._root_element = root(**props)
        else:
            self._root_element = component(root)(**props)

    def start(self) -> None:
        self.flushing = True
        try:
            with _gc_paused():
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
                self._dirty_set = set()
                with _gc_paused():
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
        if self.broken:
            return
        msg = json.loads(payload)
        if msg.get("event") == "env":
            try:
                self.env.update(msg.get("payload") or {})
            except Exception as e:  # noqa: BLE001
                self.on_error(e)
            self._request_flush()
            return
        if msg.get("event") == "hardware_back":
            from .modules import Back
            try:
                Back.handle()
            except Exception as e:  # noqa: BLE001
                self.on_error(e)
            self._request_flush()
            return
        if msg.get("event") == "call_result":
            fut = self._pending.pop(msg["id"], None)
            pl = msg.get("payload") or {}
            if fut is not None and not fut.done():
                if pl.get("error"):
                    fut.set_exception(RuntimeError(str(pl["error"])))
                else:
                    fut.set_result(pl.get("value"))
            return
        if msg.get("event") in ("anim_end", "anim_value"):
            try:
                anim_runtime.handle_event(msg)
            except Exception as e:  # noqa: BLE001
                self.on_error(e)
            self._request_flush()
            return
        try:
            self.rec.dispatch(msg["id"], msg["event"], msg.get("payload"))
        except Exception as e:  # noqa: BLE001
            self.on_error(e)
        self._request_flush()

    def _schedule(self, fiber: Fiber) -> None:
        if fiber not in self._dirty_set:
            self._dirty_set.add(fiber)
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

    def call(self, module: str, method: str, *args: Any, reply: bool = False) -> Any:
        """Call a native module. Returns an asyncio future when `reply` is set, else None."""
        from .ops import Call
        self._call_id += 1
        cid = self._call_id
        fut = None
        if reply:
            if self.loop is None:
                raise RuntimeError("reply calls need an asyncio loop")
            fut = self.loop.create_future()
            self._pending[cid] = fut
        self._send([Call(cid, module, method, list(args), reply)])
        return fut

    def _send(self, ops: list) -> None:
        if ops:
            for op in ops:
                if isinstance(op, Create):
                    self._committed[op.id] = 0
                elif isinstance(op, Insert):
                    self._committed[op.id] = op.parent
                elif isinstance(op, Remove):
                    self._committed[op.id] = 0
                elif isinstance(op, Delete):
                    self._committed.pop(op.id, None)
            self.channel.post(to_json(ops))

    # -- hot reload ----------------------------------------------------
    def hot_refresh(self, root: Any = None) -> Optional[BaseException]:
        """Re-render after code changed. Keeps state when possible, else remounts. Returns the error or None."""
        if root is not None:
            self.set_root(root[0], **root[1])
        self.flushing = True
        try:
            self.clear_error()
            for f in _walk(self.rec.root):
                reset_deps(f)
            self.dirty = []
            self._dirty_set = set()
            try:
                self.rec.render(self._root_element)
                self._send(self.rec.take_ops())
                self.rec.run_effects()
                self.broken = False
                return None
            except Exception:  # noqa: BLE001
                self.rec.ops, self.rec._deletes, self.rec.pending_effects = [], [], []
            try:
                self._remount()
                self.broken = False
                return None
            except Exception as e:  # noqa: BLE001
                self.broken = True
                return e
        finally:
            self.flushing = False

    def _remount(self) -> None:
        """Rebuild the whole tree in a fresh reconciler. Old tree is replaced only if the new render succeeds."""
        old = self.rec
        new = Reconciler(self._schedule)
        new.loop = self.loop
        new.env = self.env
        new._next_id = old._next_id
        new.render(self._root_element)  # may raise: old tree stays untouched
        ops: list = [Remove(p, n) for n, p in self._committed.items() if p]
        ops += [Delete(n) for n in self._committed]
        self._send(ops)
        self.dirty = []
        self._dirty_set = set()
        for c in old.root.children:
            try:
                old._unmount(c)  # runs effect cleanups; its ops are discarded
            except Exception as e:  # noqa: BLE001
                self.on_error(e)
        old.ops, old._deletes = [], []
        self.rec = new
        self._send(new.take_ops())
        new.run_effects()

    def show_error(self, text: str) -> None:
        self.clear_error()
        props = {"text": text, "style": {"color": "#ffffff", "background_color": "#c62828", "padding": 12}}
        self._send([Create(_ERROR_ID, "Text", props), Insert(1, _ERROR_ID, len(self.rec.root.native))])
        self._error_shown = True

    def clear_error(self) -> None:
        if self._error_shown:
            self._send([Remove(1, _ERROR_ID), Delete(_ERROR_ID)])
            self._error_shown = False


def create_app(root: Any, channel: Channel, **props: Any) -> App:
    """Mount without an event loop (synchronous flushes). Used by tests and tooling."""
    app = App(root, channel, None, **props)
    app.start()
    return app


def run_app(root: Any, channel: Optional[Channel] = None, **props: Any) -> None:
    """Run the app on the current platform. Desktop target uses the console renderer."""
    if _hot.reloading:  # app module re-executed by the reloader: do not start a second app
        _hot.captured = (root, props)
        return
    _hot.entry = os.path.realpath(sys._getframe(1).f_code.co_filename)
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
        if os.environ.get("PYXPO_DEV_URL"):
            try:
                from .dev import client
                client.start(app, loop, _hot.entry)
            except ImportError:
                pass
        if renderer is not None:
            await renderer.run()
        else:
            await asyncio.Event().wait()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
