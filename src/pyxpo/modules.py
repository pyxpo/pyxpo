"""Core helpers for optional native modules (image tools, picker, media library, sharing, ...).

Each module is its own pip package (for example `pyxpo-image-picker`, imported as `pyxpo_image_picker`)
with Python, iOS and Android sources, registered under the `pyxpo.modules` entry point group. Only the
modules listed in `[tool.pyxpo] modules = [...]` are compiled into the app, like Expo autolinking.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Callable, Dict, List, Optional

from .apis import _env

_handlers: Dict[str, List[Callable[[Any], Any]]] = {}


class ModuleNotLinkedError(RuntimeError):
    """A module was used but is not listed in `[tool.pyxpo] modules`."""


def require_linked(native: str, module: str, package: Optional[str] = None) -> None:
    """Raises `ModuleNotLinkedError` when native module `native` is not part of this build.

    `module` is the autolink name (`image-picker`), `package` the pip distribution that provides it
    (`pyxpo-image-picker`), named in the error so the fix is copy-pasteable.

    The check only applies when the native shell reported its module list (an empty list in a
    real build means nothing is linked); the desktop dev environment reports none and is skipped, and so is the
    browser, which has no native modules and only web backends, even while the dev tools emulate iOS or Android.
    """
    env = _env.current._data
    if sys.platform == "emscripten" or env.get("os") in (None, "desktop", "windows"):
        return
    if native not in (env.get("modules") or []):
        raise ModuleNotLinkedError(
            "native module '%s' is not linked into this app. %sAdd '%s' to [tool.pyxpo] modules in pyproject.toml "
            "and rebuild." % (native, "Install it with `pip install %s` if needed. " % package if package else "", module)
        )


def build_data(name: str) -> Any:
    """The JSON data module `name`'s build hook shipped with `ctx.ship(...)` (see `pyxpo.module_hooks`), or None.

    Built apps read it from the bundled `_app_config.json`; `pyxpo run desktop --preview`, which has no bundle,
    passes it in the `PYXPO_MODULE_DATA` environment variable. Returns a fresh copy on each call."""
    from .apis.constants import _load

    data = _load().get("modules")
    if data is None:
        try:
            data = json.loads(os.environ.get("PYXPO_MODULE_DATA") or "{}")
        except ValueError:
            data = {}
    v = data.get(name) if isinstance(data, dict) else None
    return None if v is None else json.loads(json.dumps(v))


def on_event(name: str, handler: Callable[[Any], Any]) -> Callable[[], None]:
    """Subscribes to events a native module emits with `ctx.emit(name, payload)`. Returns an unsubscribe."""
    _handlers.setdefault(name, []).append(handler)

    def off() -> None:
        lst = _handlers.get(name, [])
        if handler in lst:
            lst.remove(handler)

    return off


def dispatch(payload: Dict[str, Any]) -> None:
    for fn in list(_handlers.get(payload.get("name", ""), ())):
        fn(payload.get("data"))
