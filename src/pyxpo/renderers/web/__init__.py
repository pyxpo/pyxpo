"""Desktop window renderer: the app runs in Python and draws into a browser window through a local HTTP server.

Python keeps a mirror of the native tree (MockRenderer) so a reloaded window can be rebuilt, animations run in
Python (the same Driver as the tests) and module calls reach desktop backends. The page (`index.html` +
`app.js`) applies ops to the DOM with CSS flexbox using React Native defaults and posts events back.
"""
from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import secrets
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ...channel import LocalChannel
from ..mock import MockRenderer, Node
from . import backends

_HERE = Path(__file__).resolve().parent
_ANIM_OPS = {"anode", "anode_del", "alisten", "animate", "astop", "aset"}
_JS_CALLS = {"Scroll", "Keyboard", "Alert", "Picker", "StatusBar", "SplashScreen", "Back", "Vibration"}
_FRAME = 1 / 60.0


def page_js(linked: Dict[str, str]) -> Dict[str, Path]:
    """{bridge module name: its `web.js`} for the linked packages ({native: package}) that ship one. The page loads
    it after app.js: it adds the module's views (`pyxpoPage.defineView`) and answers its calls in the page
    (`pyxpoPage.defineModule`)."""
    import importlib.util
    out: Dict[str, Path] = {}
    for native, pkg in sorted(linked.items()):
        try:
            spec = importlib.util.find_spec(pkg)
        except (ImportError, ValueError):
            continue
        for d in (spec.submodule_search_locations or []) if spec else []:
            f = Path(d) / "web.js"
            if f.is_file():
                out[native] = f
                break
    return out


def _bindings(style: Any, out: Set[int]) -> None:
    if isinstance(style, dict):
        for v in style.values():
            if isinstance(v, dict) and "$a" in v:
                out.add(int(v["$a"]))


def _byte_range(header: str, size: int) -> Any:
    """(start, end) for a single "bytes=a-b" Range header, None to send the whole file, "bad" for a 416."""
    unit, _, spec = header.partition("=")
    if unit.strip().lower() != "bytes" or "," in spec:
        return None
    first, dash, last = spec.strip().partition("-")
    if not dash or not (first + last).isdigit():
        return None
    if first:
        start, end = int(first), min(int(last), size - 1) if last else size - 1
    else:
        start, end = max(size - int(last), 0), size - 1
    return (start, end) if start <= end and start < size else "bad"


def _read_span(path: Path, start: int, length: int) -> bytes:
    with open(path, "rb") as f:
        f.seek(start)
        return f.read(length)


class WebRenderer(MockRenderer):
    """Mirror tree + bridge to the page. `serve()` runs the HTTP server until the window closes."""

    js_calls = _JS_CALLS  # modules the page answers itself; the rest go to `_native_call`

    def __init__(self, channel: LocalChannel, title: str = "pyxpo", size: Tuple[int, int] = (390, 844)) -> None:
        super().__init__(channel)
        self.title = title
        self.size = size
        self.token = secrets.token_urlsafe(16)
        self.port = 0
        self.clients: List[asyncio.Queue] = []
        self.bound: Set[int] = set()
        self._ticker: Optional[asyncio.Task] = None
        try:
            self._loop: Optional[asyncio.AbstractEventLoop] = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
        # made in serve(): on Python 3.9 an Event binds to the loop current at construction
        self.closed: Optional[asyncio.Event] = None
        self.scripts = self._page_js()
        self.js_calls = type(self).js_calls | set(self.scripts)

    def _page_js(self) -> Dict[str, Path]:
        try:
            return page_js(backends._linked())
        except Exception as e:  # noqa: BLE001  a broken module install must not stop the window
            print("pyxpo desktop: module web.js: %s" % e, file=sys.stderr)
            return {}

    # -- Python -> page ------------------------------------------------------------------------------
    def apply_json(self, payload: str) -> None:
        page: List[Dict[str, Any]] = []
        anim = False
        for op in json.loads(payload):
            kind = op.get("op")
            if kind in _ANIM_OPS:
                anim = True
            elif kind == "call" and op["module"] not in self.js_calls:
                self._native_call(op)
                continue
            elif kind == "mark":
                continue
            elif kind in ("create", "update"):
                _bindings((op.get("props") or {}).get("style"), self.bound)
            if kind not in _ANIM_OPS:
                page.append(op)
        try:
            super().apply_json(json.dumps([op for op in json.loads(payload) if op.get("op") != "call"]))
        except Exception as e:  # noqa: BLE001  mirror is best effort; the page is the real view
            print("pyxpo desktop: %s" % e, file=sys.stderr)
        if page:
            self._broadcast({"ops": page})
        self._push_values()
        if anim:
            self._start_ticker()

    def _broadcast(self, msg: Dict[str, Any]) -> None:
        data = json.dumps(msg)
        for q in list(self.clients):
            q.put_nowait(data)

    def _push_values(self) -> None:
        if self.bound:
            self._broadcast({"aval": {str(n): self.driver.resolve(n) for n in self.bound}})

    def _events(self, evs: List[Dict[str, Any]]) -> None:
        super()._events(evs)
        if evs:
            self._push_values()

    def _start_ticker(self) -> None:
        if self._loop is None or not self.driver.active or (self._ticker and not self._ticker.done()):
            return
        self._ticker = self._loop.create_task(self._tick())

    async def _tick(self) -> None:
        loop = asyncio.get_running_loop()
        while self.driver.active:
            await asyncio.sleep(_FRAME)
            self._events(self.driver.tick(loop.time() * 1000.0))
            self._push_values()

    def snapshot(self) -> List[Dict[str, Any]]:
        """Ops that rebuild the current tree in an empty page."""
        ops: List[Dict[str, Any]] = []
        for n in self.nodes.values():
            if n is not self.root:
                ops.append({"op": "create", "id": n.id, "type": n.type, "props": n.props})

        def ins(p: Node) -> None:
            for i, c in enumerate(p.children):
                ops.append({"op": "insert", "parent": p.id, "id": c.id, "index": i})
                ins(c)
        ins(self.root)
        return ops

    # -- module calls --------------------------------------------------------------------------------
    def _native_call(self, op: Dict[str, Any]) -> None:
        cid, reply = op["id"], op.get("reply")

        def done(fut: "asyncio.Future[Any]") -> None:
            if not reply:
                return
            e = fut.exception()
            pl = {"error": str(e)} if e else {"value": fut.result()}
            self.channel.emit_event(json.dumps({"event": "call_result", "id": cid, "payload": pl}))

        assert self._loop is not None
        fut = self._loop.run_in_executor(None, backends.call, op["module"], op["method"], list(op.get("args") or []))
        fut.add_done_callback(done)

    # -- page -> Python ------------------------------------------------------------------------------
    def page_event(self, msg: Dict[str, Any]) -> None:
        if msg.get("event") == "scroll":
            n = self.nodes.get(msg.get("id"))
            if n is None:
                return
            prop = n.props.get("on_scroll")
            value = (msg.get("payload") or {}).get("value") or {}
            emit = bool(prop)
            if isinstance(prop, dict) and "$ae" in prop:
                self._events(self.driver.aset({str(nid): float(value[k]) for k, nid in prop["$ae"].items() if k in value}))
                emit = bool(prop.get("emit"))
            if not emit:
                return
        self.channel.emit_event(json.dumps(msg))

    # -- HTTP ----------------------------------------------------------------------------------------
    def url(self) -> str:
        return "http://127.0.0.1:%d/?t=%s" % (self.port, self.token)

    async def serve(self, open_window: bool = True) -> None:
        self._loop = asyncio.get_running_loop()
        self.closed = asyncio.Event()
        server = await asyncio.start_server(self._client, "127.0.0.1", int(os.environ.get("PYXPO_DESKTOP_PORT", "0")))
        self.port = server.sockets[0].getsockname()[1]
        print("pyxpo desktop: %s" % self.url(), flush=True)
        proc = open_browser(self.url(), self.size) if open_window else None
        async with server:
            if proc is not None:
                await self._loop.run_in_executor(None, proc.wait)  # window closed: quit
            else:
                await self.closed.wait()

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                head = await reader.readuntil(b"\r\n\r\n")
                lines = head.decode("latin-1").split("\r\n")
                method, target, _ = lines[0].split(" ", 2)
                headers = {k.strip().lower(): v.strip() for k, _, v in (ln.partition(":") for ln in lines[1:] if ln)}
                body = await reader.readexactly(int(headers.get("content-length") or 0))
                if not await self._route(method, target, headers, body, writer):
                    return
        except (asyncio.IncompleteReadError, ConnectionError, ValueError):
            pass
        finally:
            writer.close()

    async def _route(self, method: str, target: str, headers: Dict[str, str], body: bytes,
                     writer: asyncio.StreamWriter) -> bool:
        u = urllib.parse.urlsplit(target)
        q = dict(urllib.parse.parse_qsl(u.query))
        # Only this page may talk to the app: the token is in the window URL, and the Host check stops DNS rebinding.
        if headers.get("host") not in ("127.0.0.1:%d" % self.port, "localhost:%d" % self.port):
            return self._send(writer, 403, b"bad host")
        if u.path == "/app.js":
            return self._send(writer, 200, (_HERE / "app.js").read_bytes(), "text/javascript; charset=utf-8")
        if u.path.startswith("/module/") and u.path.endswith(".js") and u.path[8:-3] in self.scripts:
            return self._send(writer, 200, self.scripts[u.path[8:-3]].read_bytes(), "text/javascript; charset=utf-8")
        if q.get("t") != self.token and headers.get("x-pyxpo-token") != self.token:
            return self._send(writer, 403, b"bad token")
        if u.path == "/" and method == "GET":
            scripts = '<script>window.PYXPO_TOKEN = "%s";</script>\n<script src="/app.js"></script>' % self.token
            scripts += "".join('\n<script src="/module/%s.js"></script>' % n for n in self.scripts)
            html = page_html(self.title, scripts, "App stopped. Run pyxpo run desktop again.")
            return self._send(writer, 200, html.encode(), "text/html; charset=utf-8")
        if u.path == "/stream" and method == "GET":
            await self._stream(writer)
            return False
        if u.path == "/event" and method == "POST":
            for msg in json.loads(body or b"[]"):
                self.page_event(msg)
            return self._send(writer, 204, b"")
        if u.path == "/file" and method == "GET":
            p = Path(q.get("p", ""))
            if not p.is_file():
                return self._send(writer, 404, b"not found")
            ctype = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
            # <video> and <audio> ask for byte ranges; WebKit plays nothing without them, Chromium cannot seek.
            size = p.stat().st_size
            span = _byte_range(headers.get("range", ""), size)
            if span == "bad":
                return self._send(writer, 416, b"", extra="Content-Range: bytes */%d\r\n" % size)
            start, end = span or (0, size - 1)
            data = await asyncio.get_running_loop().run_in_executor(None, _read_span, p, start, end - start + 1)
            if span:
                return self._send(writer, 206, data, ctype, "max-age=3600",
                                  "Accept-Ranges: bytes\r\nContent-Range: bytes %d-%d/%d\r\n" % (start, end, size))
            return self._send(writer, 200, data, ctype, "max-age=3600", "Accept-Ranges: bytes\r\n")
        return self._send(writer, 404, b"not found")

    def _send(self, writer: asyncio.StreamWriter, status: int, body: bytes, ctype: str = "text/plain",
              cache: str = "no-store", extra: str = "") -> bool:
        reason = {200: "OK", 204: "No Content", 206: "Partial Content", 403: "Forbidden", 404: "Not Found",
                  416: "Range Not Satisfiable"}.get(status, "OK")
        writer.write(("HTTP/1.1 %d %s\r\nContent-Type: %s\r\nContent-Length: %d\r\nCache-Control: %s\r\n%s\r\n"
                      % (status, reason, ctype, len(body), cache, extra)).encode() + body)
        return True

    async def _stream(self, writer: asyncio.StreamWriter) -> None:
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nCache-Control: no-store\r\n\r\n")
        q: asyncio.Queue = asyncio.Queue()
        # A new or reloaded page starts empty: rebuild it from the mirror.
        q.put_nowait(json.dumps({"reset": True, "ops": self.snapshot(),
                                 "aval": {str(n): self.driver.resolve(n) for n in self.bound}}))
        self.clients.append(q)
        try:
            while True:
                try:
                    data = await asyncio.wait_for(q.get(), 15)
                    writer.write(b"data: " + data.encode() + b"\n\n")
                except asyncio.TimeoutError:
                    writer.write(b": ping\n\n")
                await writer.drain()
        finally:
            self.clients.remove(q)


def page_html(title: str, scripts: str, lost: str) -> str:
    """The page shell shared by the desktop window and the web build."""
    import html as _html
    return ((_HERE / "index.html").read_text().replace("{{TITLE}}", _html.escape(title))
            .replace("{{LOST}}", lost).replace("{{SCRIPTS}}", scripts))


def _chrome() -> Optional[str]:
    for p in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Chromium.app/Contents/MacOS/Chromium",
              "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
              "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"):
        if os.path.exists(p):
            return p
    for name in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge", "chrome"):
        p = shutil.which(name)
        if p:
            return p
    return None


def open_browser(url: str, size: Tuple[int, int]) -> Optional["subprocess.Popen[bytes]"]:
    """Opens `url` in a chromeless app window (own profile, so it is its own process) and returns that process.
    Without a Chromium browser, opens the default browser and returns None."""
    exe = None if os.environ.get("PYXPO_DESKTOP_BROWSER") == "default" else _chrome()
    if exe is None:
        import webbrowser
        webbrowser.open(url)
        return None
    profile = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "pyxpo" / "desktop-window"
    profile.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen([exe, "--app=" + url, "--user-data-dir=" + str(profile), "--no-first-run",
                             "--no-default-browser-check", "--window-size=%d,%d" % (size[0], size[1] + 28)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
