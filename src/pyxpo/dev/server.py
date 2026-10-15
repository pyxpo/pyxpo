"""Host-side dev server: watches the project's app/ tree and serves changes by HTTP long-poll."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Tuple
from urllib.parse import parse_qs, urlparse

POLL_TIMEOUT = 25.0
SCAN_INTERVAL = 0.3
TOKEN_HEADER = "X-Pyxpo-Token"


def scan(app_dir: str) -> Dict[str, Tuple[int, int]]:
    """Map 'app/<rel>' to (mtime_ns, size) for every file under app_dir."""
    out: Dict[str, Tuple[int, int]] = {}
    parent = os.path.dirname(os.path.normpath(app_dir))
    for dp, dns, fns in os.walk(app_dir):
        dns[:] = [d for d in dns if d != "__pycache__" and not d.startswith(".")]
        for fn in fns:
            if fn.startswith(".") or fn.endswith((".pyc", ".pyxpo-tmp")):
                continue
            full = os.path.join(dp, fn)
            try:
                st = os.stat(full)
            except OSError:
                continue
            out[os.path.relpath(full, parent).replace(os.sep, "/")] = (st.st_mtime_ns, st.st_size)
    return out


class DevServer:
    def __init__(self, project: str, port: int = 8765, token: str = "") -> None:
        self.project = os.path.abspath(project)
        self.app_dir = os.path.join(self.project, "app")
        self.token = token
        self.session = "%x" % int(time.time() * 1000)
        self.version = 1
        self.reload_at = 0
        self.files: Dict[str, Dict[str, str]] = {}
        self.changed_at: Dict[str, int] = {}
        self.deleted: Dict[str, int] = {}
        self.cond = threading.Condition()
        self._stop = threading.Event()
        self.polled = threading.Event()  # set once any device has polled (i.e. a dev client is connected)
        self._started = False
        self._sigs: Dict[str, Tuple[int, int]] = {}
        self._pending: Dict[str, Tuple[int, int]] = {}
        self._load_initial()
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:  # silence
                pass

            def _auth(self) -> bool:
                got = self.headers.get(TOKEN_HEADER, "")
                if server.token and not hmac.compare_digest(got, server.token):
                    self.send_response(403)
                    self.end_headers()
                    return False
                return True

            def _json(self, obj: Any) -> None:
                body = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                if not self._auth():
                    return
                u = urlparse(self.path)
                if u.path != "/poll":
                    self.send_response(404)
                    self.end_headers()
                    return
                q = parse_qs(u.query)
                try:
                    since = int(q.get("since", ["0"])[0])
                except ValueError:
                    since = 0
                sess = q.get("session", [""])[0]
                try:
                    self._json(server.poll(since, sess))
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def do_POST(self) -> None:
                if not self._auth():
                    return
                path = urlparse(self.path).path
                if path == "/reload":
                    server.request_reload()
                    self.send_response(204)
                    self.end_headers()
                    return
                if path != "/log":
                    self.send_response(404)
                    self.end_headers()
                    return
                n = min(int(self.headers.get("Content-Length", "0") or 0), 1 << 20)
                text = self.rfile.read(n).decode("utf-8", "replace")
                sys.stderr.write("[device] " + text.rstrip() + "\n")
                self.send_response(204)
                self.end_headers()

        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]

    @property
    def url(self) -> str:
        return "http://127.0.0.1:%d" % self.port

    # -- state ---------------------------------------------------------
    def _read(self, rel: str) -> bytes:
        with open(os.path.join(self.project, *rel.split("/")), "rb") as f:
            return f.read()

    def _load_initial(self) -> None:
        self._sigs = scan(self.app_dir)
        for rel in self._sigs:
            try:
                self._store(rel, self._read(rel))
            except OSError:
                pass
            self.changed_at[rel] = 1

    def _store(self, rel: str, data: bytes) -> None:
        self.files[rel] = {"sha1": hashlib.sha1(data).hexdigest(), "data": base64.b64encode(data).decode()}

    def request_reload(self) -> None:
        """Ask connected devices to do a full reload (same as pressing R twice on the device)."""
        with self.cond:
            self.version += 1
            self.reload_at = self.version
            self.cond.notify_all()

    def poll(self, since: int, session: str) -> Dict[str, Any]:
        self.polled.set()
        deadline = time.monotonic() + POLL_TIMEOUT
        with self.cond:
            if session == self.session and since:
                while self.version <= since and not self._stop.is_set():
                    left = deadline - time.monotonic()
                    if left <= 0:
                        break
                    self.cond.wait(left)
            full = session != self.session or not since
            if full:
                files = dict(self.files)
                deleted = []
            else:
                files = {r: m for r, m in self.files.items() if self.changed_at.get(r, 0) > since}
                deleted = [r for r, v in self.deleted.items() if v > since]
            return {"session": self.session, "version": self.version, "files": files, "deleted": deleted,
                    "reload": self.reload_at}

    def _tick(self) -> None:
        cur = scan(self.app_dir)
        if cur != self._sigs:
            if cur != self._pending:  # debounce: publish after two identical scans
                self._pending = cur
                return
            with self.cond:
                self.version += 1
                v = self.version
                for rel, sig in cur.items():
                    if self._sigs.get(rel) != sig:
                        try:
                            self._store(rel, self._read(rel))
                        except OSError:
                            continue
                        self.changed_at[rel] = v
                        self.deleted.pop(rel, None)
                for rel in set(self._sigs) - set(cur):
                    self.files.pop(rel, None)
                    self.deleted[rel] = v
                self._sigs = cur
                self.cond.notify_all()
        self._pending = {}

    def _watch(self) -> None:
        while not self._stop.wait(SCAN_INTERVAL):
            try:
                self._tick()
            except Exception as e:  # noqa: BLE001
                sys.stderr.write("[pyxpo dev] watcher error: %s\n" % e)

    # -- lifecycle -----------------------------------------------------
    def start(self) -> None:
        if self._started:
            return
        self._started = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True, name="pyxpo-dev-http").start()
        threading.Thread(target=self._watch, daemon=True, name="pyxpo-dev-watch").start()

    def serve_forever(self) -> None:
        self.start()
        try:
            while not self._stop.wait(0.5):
                pass
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self) -> None:
        self._stop.set()
        with self.cond:
            self.cond.notify_all()
        self.httpd.shutdown()
        self.httpd.server_close()
