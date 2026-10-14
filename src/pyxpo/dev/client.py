"""Device-side dev client: long-polls the dev server and hands updates to the HotReloader."""
from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request
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
        self._stop = threading.Event()

    def _req(self, path: str, data: Optional[bytes] = None, timeout: float = 35.0) -> Any:
        req = urllib.request.Request(self.url + path, data=data, headers={TOKEN_HEADER: self.token})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
        return json.loads(body) if body else None

    def poll_once(self) -> None:
        upd = self._req("/poll?since=%d&session=%s" % (self.version, self.session))
        if upd["session"] != self.session or upd["version"] != self.version:
            self.session, self.version = upd["session"], upd["version"]
            if upd["files"] or upd["deleted"]:
                self.loop.call_soon_threadsafe(self.reloader.apply, upd)

    def run(self) -> None:
        delay = 1.0
        while not self._stop.is_set():
            try:
                self.poll_once()
                delay = 1.0
            except (urllib.error.URLError, OSError, ValueError):
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
    base = os.path.dirname(os.path.dirname(os.path.realpath(entry)))
    client = DevClient(HotReloader(app, base, entry), loop, url, token)
    threading.Thread(target=client.run, daemon=True, name="pyxpo-dev-client").start()
    return client
