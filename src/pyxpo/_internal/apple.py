"""Fixes for the iOS CPython when it runs as a Mac Catalyst app."""
from __future__ import annotations

import os
import sys
import types

MAC_CA_FILE = "/etc/ssl/cert.pem"  # the system root certificates, kept current by macOS updates


def install() -> None:
    if sys.platform != "darwin":
        return
    _scproxy_stand_in()
    _ca_file()


def _scproxy_stand_in() -> None:
    # The Catalyst build reports sys.platform "darwin", so `import urllib.request` imports _scproxy (the macOS
    # system proxy settings), which the iOS CPython does not ship. Without it urllib, and every HTTP library built on
    # it, fails to import. The stand-in reports no system proxy; the *_proxy environment variables still apply.
    if "_scproxy" in sys.modules:
        return
    try:
        import _scproxy  # noqa: F401
    except ImportError:
        mod = types.ModuleType("_scproxy")
        mod._get_proxy_settings = lambda: {"exclude_simple": False, "exceptions": ()}
        mod._get_proxies = lambda: {}
        sys.modules["_scproxy"] = mod


def _ca_file() -> None:
    # The bundled OpenSSL looks for root certificates under its build prefix, which does not exist on the Mac, so
    # every HTTPS request would fail verification. Point it at the system bundle unless the app chose its own.
    if "SSL_CERT_FILE" in os.environ or "SSL_CERT_DIR" in os.environ:
        return
    if os.path.isfile(MAC_CA_FILE):
        os.environ["SSL_CERT_FILE"] = MAC_CA_FILE
