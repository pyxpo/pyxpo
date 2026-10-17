"""Device-side dev client: long-polls the dev server and hands updates to the HotReloader."""
from __future__ import annotations

import http.client
import json
import os
import sys
import threading
import urllib.parse
from typing import Any, Optional

from .reloader import HotReloader

TOKEN_HEADER = "X-Pyxpo-Token"


class DevClient:
    def __init__(self, reloader: HotReloader, loop: Any, url: str, token: str) -> None:
        self.reloader = reloader
        self.loop = loop
        self.url = url.rstrip("/")
        self.token = token
        self.session = ""
        self.version = 0
        self.reload_seen = 0
        self._stop = threading.Event()

    def _req(self, path: str, data: Optional[bytes] = None, timeout: float = 35.0) -> Any:
        # http.client, not urllib.request: on macOS urllib.request imports _scproxy at load, and the Mac (Catalyst)
        # Python has no _scproxy, so the import fails there.
        u = urllib.parse.urlsplit(self.url)
        conn = http.client.HTTPConnection(u.hostname or "127.0.0.1", u.port or 80, timeout=timeout)
        try:
            conn.request("POST" if data is not None else "GET", u.path + path, body=data, headers={TOKEN_HEADER: self.token})
            r = conn.getresponse()
            body = r.read()
            if r.status >= 400:
                raise OSError("dev server answered %d" % r.status)
        finally:
            conn.close()
        return json.loads(body) if body else None

    def poll_once(self) -> None:
        upd = self._req("/poll?since=%d&session=%s" % (self.version, self.session))
        if upd["session"] != self.session or upd["version"] != self.version:
            fresh = upd["session"] != self.session
            self.session, self.version = upd["session"], upd["version"]
            reload_at = upd.get("reload", 0)
            if upd["files"] or upd["deleted"]:
                self.loop.call_soon_threadsafe(self.reloader.apply, upd)
            if not fresh and reload_at != self.reload_seen:
                self.loop.call_soon_threadsafe(self.reloader.reload_all)
            self.reload_seen = reload_at

    def run(self) -> None:
        delay = 1.0
        warned = False
        while not self._stop.is_set():
            try:
                self.poll_once()
                delay = 1.0
                warned = False
            except (OSError, http.client.HTTPException, ValueError) as e:
                if not warned:  # once per outage: the server may be stopped on purpose
                    sys.stderr.write("[pyxpo dev] cannot reach %s: %s\n" % (self.url, e))
                    warned = True
                self._stop.wait(delay)
                delay = min(delay * 2, 5.0)
            except RuntimeError:  # event loop closed: app is gone
                return
            except Exception as e:  # noqa: BLE001
                sys.stderr.write("[pyxpo dev] client error: %s\n" % e)
                self._stop.wait(delay)

    def stop(self) -> None:
        self._stop.set()


def start(app: Any, loop: Any, entry: Optional[str], url: Optional[str] = None, token: Optional[str] = None) -> Optional[DevClient]:
    url = url or os.environ.get("PYXPO_DEV_URL")
    if not url or not entry:
        return None
    token = token if token is not None else os.environ.get("PYXPO_DEV_TOKEN", "")
    pkg = sys.modules.get("app")
    app_dir = list(pkg.__path__)[0] if getattr(pkg, "__path__", None) else os.path.dirname(entry)
    base = os.path.dirname(os.path.realpath(app_dir))
    client = DevClient(HotReloader(app, base, entry), loop, url, token)
    app.dev_reload = client.reloader.reload_all
    threading.Thread(target=client.run, daemon=True, name="pyxpo-dev-client").start()
    return client
