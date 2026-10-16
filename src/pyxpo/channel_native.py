from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

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


# Module calls the Windows shell answers itself; every other module runs in Python (its desktop backend).
WINDOWS_SHELL_CALLS = frozenset(("Scroll", "StatusBar", "Back", "Keyboard", "SplashScreen", "Vibration", "Alert",
                                 "Clipboard", "Linking"))


class WindowsChannel(NativeChannel):
    """The native Windows app. Module calls go to the same desktop backends as `pyxpo run desktop --preview`,
    on worker threads; their `call_result` comes back through the event handler, like a native answer."""

    def __init__(self, bridge: Any = None, backend: Optional[Callable[[str, str, list], Any]] = None) -> None:
        if bridge is None:
            super().__init__()
        else:
            self._bridge = bridge
        if backend is None:
            from .renderers.web import backends
            backend = backends.call
        self._backend = backend
        self._handler: Optional[Callable[[str], None]] = None
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pyxpo-module")

    def set_event_handler(self, fn: Callable[[str], None]) -> None:
        self._handler = fn
        super().set_event_handler(fn)

    def post(self, payload: str) -> None:
        if '"op":"call"' not in payload:  # cheap test: most batches carry no call
            self._bridge.post(payload)
            return
        ops = json.loads(payload)
        keep = []
        for op in ops:
            if op.get("op") == "call" and op.get("module") not in WINDOWS_SHELL_CALLS:
                self._pool.submit(self._run, op)
            else:
                keep.append(op)
        if keep:
            self._bridge.post(json.dumps(keep, separators=(",", ":")))

    def _run(self, op: Dict[str, Any]) -> None:
        try:
            pl: Dict[str, Any] = {"value": self._backend(op["module"], op["method"], list(op.get("args") or []))}
        except Exception as e:  # noqa: BLE001  the app's future gets the error
            pl = {"error": str(e) or type(e).__name__}
        if op.get("reply") and self._handler is not None:
            self._handler(json.dumps({"event": "call_result", "id": op["id"], "payload": pl}))
