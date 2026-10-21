"""Fixes for the iOS CPython when it runs as a Mac Catalyst app."""
from __future__ import annotations

import sys
import types


def install() -> None:
    # The Catalyst build reports sys.platform "darwin", so `import urllib.request` imports _scproxy (the macOS
    # system proxy settings), which the iOS CPython does not ship. Without it urllib, and every HTTP library built on
    # it, fails to import. The stand-in reports no system proxy; the *_proxy environment variables still apply.
    if sys.platform != "darwin" or "_scproxy" in sys.modules:
        return
    try:
        import _scproxy  # noqa: F401
    except ImportError:
        mod = types.ModuleType("_scproxy")
        mod._get_proxy_settings = lambda: {"exclude_simple": False, "exceptions": ()}
        mod._get_proxies = lambda: {}
        sys.modules["_scproxy"] = mod
