"""Test helper for native module packages: replaces the bridge so Python logic runs on the desktop.

    def test_share(fake_bridge):
        fake_bridge.on("Share", "share", lambda urls, msg: {"action": "sharedAction"})
        ...
Use `with FakeBridge() as fb:` or the `fake_bridge` fixture from your own conftest.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from .apis import _bridge, _env


class FakeBridge:
    def __init__(self, os_name: str = "ios", modules: Tuple[str, ...] = (),
                 constants: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        """`constants` is {bridge module name: values} as native sends them at startup (`module_api.constants`)."""
        self.calls: List[Tuple[str, str, tuple]] = []
        self._handlers: Dict[Tuple[str, str], Callable[..., Any]] = {}
        self._os, self._modules = os_name, list(modules) + [m for m in (constants or {}) if m not in modules]
        self._constants = dict(constants or {})

    def on(self, module: str, method: str, handler: Callable[..., Any]) -> "FakeBridge":
        self._modules.append(module) if module not in self._modules else None
        self._handlers[(module, method)] = handler
        return self

    def _call(self, module: str, method: str, *args: Any, reply: bool = False) -> Any:
        self.calls.append((module, method, args))
        fn = self._handlers.get((module, method))
        if fn is None:
            raise RuntimeError("FakeBridge: no handler for %s.%s" % (module, method))
        res = fn(*args)
        if not reply:
            return res

        async def done() -> Any:
            return res

        return done()

    def __enter__(self) -> "FakeBridge":
        self._old = (_bridge._app, _env.current)

        class _App:
            call = staticmethod(self._call)

        _bridge.set_app(_App())
        _env.current = _env.Env({"os": self._os, "modules": self._modules, "module_constants": self._constants})
        return self

    def __exit__(self, *exc: Any) -> None:
        _bridge._app, _env.current = self._old
