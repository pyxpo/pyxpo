"""Public API for native module packages (`pyxpo-image-picker`, third-party modules, ...).

Module packages import only from here, never from private `pyxpo._*` or `pyxpo.apis._*` paths. This
surface is versioned: `NATIVE_CONTRACT` is the version of the bridge/native-module contract a package
was written against and is compared with the `nativeContract` field of its `pyxpo-module.json`.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from ._keys import snake_aliases
from .apis import _env
from .apis._bridge import call
from .modules import ModuleNotLinkedError, dispatch, on_event, require_linked

NATIVE_CONTRACT = 1

__all__ = [
    "NATIVE_CONTRACT", "NotSupportedError", "ModuleNotLinkedError", "call", "on_event", "dispatch",
    "require_linked", "snake_aliases", "platform", "permission_response", "require_supported",
]


class NotSupportedError(RuntimeError):
    """The option or operation cannot work on this platform. Raised before any native call."""


def platform() -> str:
    """`"ios"`, `"android"` or `"desktop"`."""
    return _env.current._data.get("os") or "desktop"


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
