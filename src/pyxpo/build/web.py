"""Web build: a static single page app. The app's Python runs in the browser on Pyodide (CPython compiled to
WebAssembly); the pyxpo reconciler is the virtual DOM and `app.js` applies its ops to real DOM nodes. The router
keeps the address bar and browser history in step, so links, refresh and back/forward work like any SPA.

    build/web/
        index.html               page shell; window.PYXPO_CONFIG says where everything is
        404.html                 same page, so static hosts (GitHub Pages) serve deep links
        boot.js, app.js          loader and DOM renderer
        app.<hash>.zip           the project's app/ and assets/, the pyxpo package, linked modules

Any static host works when unknown paths fall back to index.html. `base` ([tool.pyxpo.web] base or --base) is the
path the site lives under, such as "/myapp" on a project page.
"""
from __future__ import annotations

import hashlib
import http.server
import json
import os
import shutil
import tempfile
import threading
import time
import urllib.parse
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from .. import native_config
from ..config import load_config
from ..module_hooks import build_mode
from ..renderers.web import page_html
from . import app_json, autolink
from .android import BuildError
from .ios import _stage_app

PYODIDE_VERSION = "0.27.7"
PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v%s/full/" % PYODIDE_VERSION
_WEB = Path(__file__).resolve().parent.parent / "renderers" / "web"
_ZIP_TIME = (2020, 1, 1, 0, 0, 0)  # fixed, so the same sources give the same bundle hash


def base_path(raw: Any) -> str:
    """'' for the site root, else '/a/b' (leading slash, no trailing one)."""
    s = str(raw or "").strip()
    if any(c in s for c in '"\'<>\\?#') or "://" in s:
        raise BuildError("web base must be a plain path such as /myapp, got %r" % s)
    s = "/".join(p for p in s.split("/") if p)
    return "/" + s if s else ""


def web_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    web = cfg.get("web") if isinstance(cfg.get("web"), dict) else {}
    pkgs = web.get("packages", [])
    if not isinstance(pkgs, list) or not all(isinstance(p, str) for p in pkgs):
        raise BuildError("[tool.pyxpo.web] packages must be a list of package names")
    return web


def packages(cfg: Dict[str, Any], modules: List[autolink.Module]) -> List[str]:
    """What boot.js loads (Pyodide builds directly, the rest with micropip): [tool.pyxpo] requires,
    [tool.pyxpo.web] packages and what linked modules list under `web.packages` in their manifest (such as pillow for
    image-manipulator)."""
    out: List[str] = []
    for p in list(cfg.get("requires", [])) + list(web_config(cfg).get("packages", [])):
        out.append(str(p))
    for m in modules:
        out += [str(p) for p in m.web.get("packages", [])]
    return sorted(set(out))


def _zip(src: Path, dest: Path) -> None:
    with zipfile.ZipFile(str(dest), "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(p for p in src.rglob("*") if p.is_file()):
            info = zipfile.ZipInfo(f.relative_to(src).as_posix(), _ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, f.read_bytes())


def _script_json(v: Any) -> str:
    return json.dumps(v, sort_keys=True).replace("</", "<\\/")


def build(project: Path, release: bool = False, base: Optional[str] = None, out: Optional[Path] = None) -> Path:
    """Writes the static site to `build/web/` (or `out`) and returns that folder."""
    project = Path(project).resolve()
    cfg = load_config(project, build_mode(release))
    nc = native_config.resolve(cfg, project)
    web = web_config(cfg)
    base = base_path(web.get("base", "") if base is None else base)
    out = Path(out) if out is not None else project / "build" / "web"
    linked = autolink.link(cfg, project)

    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "app"
        _stage_app(project, stage, True, linked.modules)  # no hot-reload client: the browser reloads the page
        app_json.write(stage / "pyxpo", nc)
        (stage / "pyxpo" / "web_modules.json").write_text(
            json.dumps({m.native: m.pkg for m in linked.modules}, indent=2, sort_keys=True))
        page = {m.native: m.root / "web.js" for m in linked.modules if (m.root / "web.js").is_file()}
        (stage / "pyxpo" / "web_page_modules.json").write_text(json.dumps(sorted(page)))
        bundle = Path(tmp) / "app.zip"
        _zip(stage, bundle)
        h = hashlib.sha256(bundle.read_bytes())
        for name in ("app.js", "boot.js", "index.html"):
            h.update((_WEB / name).read_bytes())
        for native in sorted(page):
            h.update(page[native].read_bytes())
        version = h.hexdigest()[:12]
        if out.exists():
            shutil.rmtree(str(out))
        out.mkdir(parents=True)
        bundle_name = "app.%s.zip" % version
        shutil.copy2(str(bundle), str(out / bundle_name))

    for name in ("app.js", "boot.js"):
        shutil.copy2(str(_WEB / name), str(out / name))
    if page:
        (out / "modules").mkdir()
    for native, src in page.items():
        shutil.copy2(str(src), str(out / "modules" / ("%s.js" % native)))
    config = {"base": base, "bundle": bundle_name, "version": version, "packages": packages(cfg, linked.modules),
              "scripts": ["modules/%s.js" % n for n in sorted(page)],
              "pyodide": str(web.get("pyodide_url") or PYODIDE_URL)}
    scripts = ('<script>window.PYXPO_CONFIG = %s;</script>\n<script src="%s/boot.js?v=%s"></script>'
               % (_script_json(config), base, version))
    html = page_html(str(web.get("title") or nc["name"]), scripts, "Loading…")
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / "404.html").write_text(html, encoding="utf-8")
    print("built %s (%s)" % (out, bundle_name))
    return out


# -- dev server ------------------------------------------------------------------------------------------------------
# Reloads the page when a file changes, and when R is pressed twice outside a text field (as in React Native).
_RELOAD = ('<script>(() => { const es = new EventSource("/__pyxpo/reload"); '
           'es.onmessage = () => location.reload(); let lastR = 0; '
           'document.addEventListener("keydown", (e) => { '
           'if ((e.key !== "r" && e.key !== "R") || e.repeat || e.metaKey || e.ctrlKey || e.altKey) return; '
           'const t = (e.composedPath && e.composedPath()[0]) || e.target; '
           'if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName || ""))) return; '
           'const now = Date.now(); if (now - lastR < 800) { lastR = 0; location.reload(); } else lastR = now; '
           '}); })();</script>\n</body>')
_DEVTOOLS = '<script src="/__pyxpo/devtools.js"></script>\n'  # device preview panel, dev server only


def _watch_stamp(project: Path, modules: Optional[List[Path]] = None) -> Any:
    """Changes when the app, its assets, pyproject.toml, a `.env*` file (pyxpo-dot-env) or a linked module package
    (local editable install) changes."""
    env_files = sorted(project.glob(".env*"))
    paths = [project / "pyproject.toml"] + env_files
    for sub in ("app", "assets"):
        d = project / sub
        if d.is_dir():
            paths += [p for p in d.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    newest = max((p.stat().st_mtime for p in paths if p.exists()), default=0.0)
    return newest, [p.name for p in env_files], autolink.module_files(modules or [])


class DevServer:
    """Serves `build/web` like a static host with SPA fallback, rebuilds on change and reloads open pages."""

    def __init__(self, project: Path, port: int = 8000, host: str = "127.0.0.1", base: Optional[str] = None,
                 devtools: bool = True) -> None:
        self.project = Path(project).resolve()
        self.devtools = devtools
        self.base = base
        self.root = build(self.project, base=base)
        self.prefix = json.loads(self._config())["base"]
        self.generation = 0
        self.cond = threading.Condition()
        self.httpd = http.server.ThreadingHTTPServer((host, port), self._handler())
        self.httpd.daemon_threads = True

    def _config(self) -> str:
        html = (self.root / "index.html").read_text(encoding="utf-8")
        return html.split("window.PYXPO_CONFIG = ", 1)[1].split(";</script>", 1)[0]

    @property
    def url(self) -> str:
        host, port = self.httpd.server_address[:2]
        return "http://%s:%d%s/" % (host, port, self.prefix)

    def watch(self, interval: float = 0.5) -> None:
        modules = autolink.linked_roots(self.project)
        stamp = _watch_stamp(self.project, modules)
        while True:
            time.sleep(interval)
            now = _watch_stamp(self.project, modules)
            if now == stamp:
                continue
            stamp = now
            try:
                build(self.project, base=self.base)
            except Exception as e:  # noqa: BLE001  keep serving the last good build
                print("pyxpo web: build failed: %s" % e, flush=True)
                continue
            with self.cond:
                self.generation += 1
                self.cond.notify_all()

    def serve_forever(self) -> None:
        threading.Thread(target=self.watch, daemon=True).start()
        self.httpd.serve_forever()

    def _handler(self) -> Any:
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a: Any) -> None:
                pass

            def do_GET(self) -> None:  # noqa: N802
                path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
                if path == "/__pyxpo/reload":
                    return self._reload()
                if path == "/__pyxpo/devtools.js" and server.devtools:
                    return self._send((_WEB / "devtools.js").read_bytes(), _ctype("devtools.js"), "no-cache")
                rel = path[len(server.prefix):] if path.startswith(server.prefix + "/") else None
                f = (server.root / rel.lstrip("/")).resolve() if rel else None
                if f is not None and f.is_file() and server.root.resolve() in f.parents:
                    return self._send(f.read_bytes(), _ctype(f.name), "no-cache")
                # SPA fallback: every other path is a route of the app
                html = (server.root / "index.html").read_text(encoding="utf-8")
                html = html.replace("</body>", (_DEVTOOLS if server.devtools else "") + _RELOAD, 1)
                self._send(html.encode(), "text/html; charset=utf-8", "no-store")

            def _send(self, body: bytes, ctype: str, cache: str) -> None:
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", cache)
                self.end_headers()
                self.wfile.write(body)

            def _reload(self) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                gen = server.generation
                try:
                    while True:
                        with server.cond:
                            server.cond.wait(15)
                            now = server.generation
                        self.wfile.write(b"data: reload\n\n" if now != gen else b": ping\n\n")
                        self.wfile.flush()
                        gen = now
                except (BrokenPipeError, ConnectionError):
                    pass

        return Handler


def _ctype(name: str) -> str:
    import mimetypes
    if name.endswith(".js"):
        return "text/javascript; charset=utf-8"
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def serve(project: Path, port: int = 8000, base: Optional[str] = None, open_browser: bool = True,
          devtools: bool = True) -> None:
    dev = DevServer(project, port, base=base, devtools=devtools)
    print("pyxpo web: %s" % dev.url, flush=True)
    if open_browser and os.environ.get("PYXPO_WEB_BROWSER") != "0":
        import webbrowser
        webbrowser.open(dev.url)
    try:
        dev.serve_forever()
    except KeyboardInterrupt:
        pass
