"""Web target: the app runs in the browser on Pyodide and draws into the page as a single page app.

Python is the virtual DOM: the reconciler diffs component trees and emits the minimal ops (create, update, insert,
remove, delete). `BrowserRenderer` hands each batch to `app.js` in the same JS context (`pyxpoPage.receive`), which
applies them to real DOM nodes; page events come back through `pyxpoPy`. There is no server: `pyxpo build web`
writes static files that any host can serve (unknown paths must fall back to index.html for deep links).

Module calls: the page answers UI calls (Alert, Scroll, History, Clipboard, Linking, ...); a native module package
answers through its optional `<package>/web.py`, which defines `call(method, args)` and may return an awaitable.
"""
from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...channel import LocalChannel
from . import WebRenderer, _JS_CALLS

WEB_JS_CALLS = _JS_CALLS | {"History", "Clipboard", "Linking"}
LINKED_FILE = Path(__file__).resolve().parents[2] / "web_modules.json"
PAGE_FILE = Path(__file__).resolve().parents[2] / "web_page_modules.json"  # modules with a web.js in the page

_mods: Optional[Dict[str, Any]] = None
_running: Dict[str, Any] = {}  # keeps the app, renderer and JS proxies alive for the page's lifetime


def _web_modules() -> Dict[str, Any]:
    """{bridge module name: its `web` backend}. The web build writes the linked list into the bundle."""
    global _mods
    if _mods is None:
        found: Dict[str, Any] = {}
        linked = json.loads(LINKED_FILE.read_text()) if LINKED_FILE.is_file() else {}
        for native, pkg in linked.items():
            try:
                found[native] = importlib.import_module(pkg + ".web")
            except ImportError:
                pass
        _mods = found
    return _mods


def _page_modules() -> List[str]:
    return list(json.loads(PAGE_FILE.read_text())) if PAGE_FILE.is_file() else []


class BrowserRenderer(WebRenderer):
    """Same mirror and animation driver as the desktop window; the transport is a direct JS call."""

    js_calls = WEB_JS_CALLS

    def __init__(self, channel: LocalChannel, page: Any, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__(channel)
        self.page = page
        self._loop = loop
        self.js_calls = WEB_JS_CALLS | set(_page_modules())  # boot.js loaded their web.js

    def _page_js(self) -> Dict[str, Path]:
        return {}

    def _broadcast(self, msg: Dict[str, Any]) -> None:
        self.page.receive(json.dumps(msg))

    def page_events(self, body: str) -> None:
        for msg in json.loads(body):
            self.page_event(msg)

    def _native_call(self, op: Dict[str, Any]) -> None:
        assert self._loop is not None
        self._loop.create_task(self._run_call(op))

    async def _run_call(self, op: Dict[str, Any]) -> None:
        try:
            mod = _web_modules().get(op["module"])
            if mod is None:
                raise RuntimeError("native module %r is not available on web" % op["module"])
            value = mod.call(op["method"], list(op.get("args") or []))
            if inspect.isawaitable(value):
                value = await value
            pl: Dict[str, Any] = {"value": value}
        except Exception as e:  # noqa: BLE001  the error goes back to the caller
            pl = {"error": str(e)}
        if op.get("reply"):
            self.channel.emit_event(json.dumps({"event": "call_result", "id": op["id"], "payload": pl}))


# -- helpers for module web backends ---------------------------------------------------------------------------------
_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
         ".heic": "image/heic", ".mp4": "video/mp4", ".mov": "video/quicktime", ".txt": "text/plain"}


def local_path(uri: str) -> str:
    return uri[7:] if uri.startswith("file://") else uri


def file_blob(path: str) -> Any:
    """A JS File with the bytes of `path` in the in-memory file system."""
    import js  # type: ignore[import-not-found]
    from pyodide.ffi import to_js  # type: ignore[import-not-found]

    p = Path(local_path(path))
    data = to_js(p.read_bytes())
    opts = js.Object.new()
    opts.type = _MIME.get(p.suffix.lower(), "application/octet-stream")
    return js.File.new(js.Array.of(data), p.name, opts)


def download(path: str) -> None:
    """Saves `path` to the user's Downloads folder (the browser's download flow)."""
    import js  # type: ignore[import-not-found]

    blob = file_blob(path)
    url = js.URL.createObjectURL(blob)
    a = js.document.createElement("a")
    a.href, a.download = url, blob.name
    a.style.display = "none"
    js.document.body.appendChild(a)
    a.click()
    a.remove()
    js.setTimeout(js.Function.new("u", "URL.revokeObjectURL(u)"), 60000, url)


async def choose_files(accept: str, multiple: bool) -> List[Any]:
    """Opens the browser's file chooser; the JS File objects the user picked, [] when canceled. Call it from a
    press handler: browsers open the chooser only shortly after a user gesture."""
    import js  # type: ignore[import-not-found]
    from pyodide.ffi import create_proxy  # type: ignore[import-not-found]

    fut: asyncio.Future = asyncio.get_event_loop().create_future()
    inp = js.document.createElement("input")
    inp.type, inp.accept, inp.multiple = "file", accept, bool(multiple)

    def done(*_: Any) -> None:
        if not fut.done():
            fut.set_result([inp.files.item(i) for i in range(inp.files.length)] if inp.files else [])

    proxy = create_proxy(done)
    inp.addEventListener("change", proxy)
    inp.addEventListener("cancel", proxy)
    inp.click()
    try:
        return await fut
    finally:
        inp.removeEventListener("change", proxy)
        inp.removeEventListener("cancel", proxy)
        proxy.destroy()


async def save_file(file: Any, folder: str) -> str:
    """Writes a picked JS File into the in-memory file system and returns its path."""
    d = Path(folder) / uuid.uuid4().hex[:8]
    d.mkdir(parents=True, exist_ok=True)
    name = "".join(c for c in str(file.name) if c not in '/\\\0') or "file"
    p = d / name
    p.write_bytes((await file.arrayBuffer()).to_bytes())
    return str(p)


def start(root: Any, props: Dict[str, Any]) -> Any:
    """Mounts the app on the running Pyodide loop and returns at once (the browser owns the event loop)."""
    import js  # type: ignore[import-not-found]  # Pyodide only
    from pyodide.ffi import create_proxy  # type: ignore[import-not-found]

    from ...app import App

    loop = asyncio.get_event_loop()
    ch = LocalChannel()
    renderer = BrowserRenderer(ch, js.pyxpoPage, loop)
    app = App(root, ch, loop, **props)
    proxy = create_proxy(renderer.page_events)
    js.pyxpoPy = proxy
    _running.update(app=app, renderer=renderer, proxy=proxy)
    app.start()
    return app


def boot(env_json: str) -> None:
    """Called by boot.js after the bundle is unpacked: sets the target and runs the router entry."""
    os.environ["PYXPO_TARGET"] = "web"
    env = json.loads(env_json)
    # Like a native shell, report what this build linked: `require_linked` checks module use against it.
    env["modules"] = sorted(set(_web_modules()) | set(_page_modules()))
    os.environ["PYXPO_ENV"] = json.dumps(env)
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 2000))
    from ...router import entry
    entry.main()
