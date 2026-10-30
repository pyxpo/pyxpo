"""Public API for native module packages (`pyxpo-image-picker`, third-party modules, ...).

Module packages import only from here, never from private `pyxpo._*` or `pyxpo.apis._*` paths. This
surface is versioned: `NATIVE_CONTRACT` is the version of the bridge/native-module contract a package
was written against and is compared with the `nativeContract` field of its `pyxpo-module.json`.
"""
from __future__ import annotations

import sys
from typing import Any, Callable, Dict, Optional

from ._keys import snake_aliases
from .element import _host
from .apis import _env
from .apis._bridge import call, report, spawn
from .modules import ModuleNotLinkedError, build_data, dispatch, on_event, require_linked

# 1: calls, events, permissions, presenter/activity hooks.
# 2: adds module constants (`constants(native)`), read synchronously at startup, the iOS
#    `PxAppLaunchObserver` hook (modules that start with the app), and module views (`native_view`).
# 3: adds the Android `PxModule.onNewIntent` hook (intents the running activity gets, like notification taps).
# 4: adds Android `PxModuleContext.context` / `hasActivity`, `PxProcess` (a Service starts Python headless and
#    sends it events) and `android.cmake` (modules that build C/C++).
NATIVE_CONTRACT = 4

__all__ = [
    "NATIVE_CONTRACT", "NotSupportedError", "ModuleNotLinkedError", "call", "on_event", "dispatch",
    "require_linked", "snake_aliases", "platform", "permission_response", "require_supported", "constants",
    "native_view", "view_tag", "spawn", "report", "build_data",
]


class NotSupportedError(RuntimeError):
    """The option or operation cannot work on this platform. Raised before any native call."""


def platform() -> str:
    """`"ios"`, `"android"`, `"web"` or `"desktop"`. The native Windows app reports `"desktop"`: modules answer
    there through their desktop backends. In the browser it is always `"web"`, even while the dev tools emulate an
    iOS or Android device: that changes `Platform.OS`, not the networking or storage underneath."""
    if sys.platform == "emscripten":
        return "web"
    o = _env.current._data.get("os")
    return "desktop" if o in (None, "windows") else o


def require_supported(feature: str, *, ios: bool = True, android: bool = True) -> None:
    """Raises `NotSupportedError` when `feature` does not exist on the running platform (desktop passes)."""
    p = platform()
    if (p == "ios" and not ios) or (p == "android" and not android):
        raise NotSupportedError("%s is not supported on %s" % (feature, p))


def permission_response(status: str, can_ask_again: bool = True, expires: str = "never") -> Dict[str, Any]:
    """Expo `PermissionResponse` shape. `status`: `granted`, `denied` or `undetermined`."""
    if status not in ("granted", "denied", "undetermined"):
        raise ValueError("bad permission status %r" % status)
    return {"status": status, "granted": status == "granted", "canAskAgain": can_ask_again, "expires": expires}


def constants(native: str) -> Dict[str, Any]:
    """Values the native module `native` exported at startup (its `constants`), or `{}` when it is not
    linked, exports none, or the app runs on desktop. Read synchronously; they do not change while the app runs."""
    table = _env.current._data.get("module_constants") or {}
    value = table.get(native) if isinstance(table, dict) else None
    return dict(value) if isinstance(value, dict) else {}


def native_view(type_name: str) -> Callable[..., Any]:
    """Element factory for a native view type that a linked module provides (iOS `PxViewModule.viewTypes`,
    Android `PxModule.viewTypes`, web and desktop window `pyxpoPage.defineView` in the package's `web.js`).
    Props reach the native view's `update` as JSON values; a callable `on_<name>` prop is called with the
    value the native side emits as `<name>`. The layout engine sizes the view from its `style`; it takes no
    children. Where the module is not linked (a platform it has no code for, or not listed in
    `[tool.pyxpo] modules`) it renders as an empty View."""
    if not type_name or not type_name[0].isupper():
        raise ValueError("native view type must start with an uppercase letter, got %r" % type_name)
    return _host(type_name)


def view_tag(handle: Any) -> Optional[int]:
    """The native tag of a mounted view: `ref.current` of a `native_view` element (or the ref itself). Pass it
    to a module call so the native side finds the view with `ctx.view(tag)`. None when not mounted."""
    cur = getattr(handle, "current", handle)
    tag = getattr(cur, "_id", None)
    return tag if isinstance(tag, int) else None
