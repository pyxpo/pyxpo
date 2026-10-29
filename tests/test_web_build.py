"""Web target: the static SPA build, the dev server, the in-browser renderer (with a fake page) and the CLI.
Pyodide itself is not needed: the browser side is checked end to end by hand (see docs)."""
from __future__ import annotations

import asyncio
import json
import os
import threading
import urllib.request
import zipfile

import pytest

from pyxpo import cli, modules
from pyxpo.apis import _env
from pyxpo.app_config.schema import ConfigError
from pyxpo.build import autolink, web
from pyxpo.build.android import BuildError
from pyxpo.channel import LocalChannel
from pyxpo.renderers.web import browser


def _project(tmp_path, tool=""):
    p = tmp_path / "proj"
    (p / "app").mkdir(parents=True)
    (p / "app" / "index.py").write_text("print('hi')\n")
    (p / "pyproject.toml").write_text('[project]\nname="x"\nversion="1.0.0"\n[tool.pyxpo]\nname = "Demo App"\n'
                                      'bundle_id = "com.acme.demo"\n' + tool)
    return p


def _config(out):
    html = (out / "index.html").read_text(encoding="utf-8")
    return json.loads(html.split("window.PYXPO_CONFIG = ", 1)[1].split(";</script>", 1)[0])


@pytest.mark.parametrize("raw,want", [(None, ""), ("", ""), ("/", ""), ("myapp", "/myapp"), ("/a/b/", "/a/b"),
                                      ("//a//b", "/a/b")])
def test_base_path(raw, want):
    assert web.base_path(raw) == want


@pytest.mark.parametrize("raw", ['/a"b', "/a<b", "/a?x", "/a#x", "https://x.example/a", "/a\\b"])
def test_base_path_rejects_unsafe(raw):
    with pytest.raises(BuildError):
        web.base_path(raw)


def test_build_writes_static_spa(tmp_path):
    p = _project(tmp_path, 'modules = ["image-manipulator"]\nrequires = ["attrs"]\n'
                           '[tool.pyxpo.web]\ntitle = "Demo </title>"\npackages = ["numpy"]\n')
    out = web.build(p)
    assert out == p / "build" / "web"
    names = sorted(f.name for f in out.iterdir())
    bundle = [n for n in names if n.startswith("app.") and n.endswith(".zip")]
    assert len(bundle) == 1 and {"index.html", "404.html", "app.js", "boot.js"} <= set(names)
    index = (out / "index.html").read_text(encoding="utf-8")
    assert (out / "404.html").read_text(encoding="utf-8") == index  # static hosts serve deep links from 404.html
    assert "<title>Demo &lt;/title&gt;</title>" in index
    cfg = _config(out)
    assert cfg["base"] == "" and cfg["bundle"] == bundle[0] and cfg["pyodide"] == web.PYODIDE_URL
    assert cfg["packages"] == ["attrs", "numpy", "pillow"]  # requires, web packages, module manifest
    assert '<script src="/boot.js?v=%s">' % cfg["version"] in index
    with zipfile.ZipFile(str(out / bundle[0])) as z:
        files = set(z.namelist())
        assert json.loads(z.read("pyxpo/web_modules.json")) == {"ImageManipulator": "pyxpo_image_manipulator"}
    assert {"app/index.py", "pyxpo/_app_config.json", "pyxpo_image_manipulator/web.py"} <= files


def test_build_is_deterministic_and_base_aware(tmp_path):
    p = _project(tmp_path)
    first = _config(web.build(p))["bundle"]
    os.utime(str(p / "app" / "index.py"), (1, 1))  # mtimes do not change the bundle
    assert _config(web.build(p))["bundle"] == first
    (p / "app" / "index.py").write_text("print('changed')\n")
    assert _config(web.build(p))["bundle"] != first
    out = web.build(p, base="/demo/", out=tmp_path / "site")
    assert _config(out)["base"] == "/demo"
    assert '<script src="/demo/boot.js?v=' in (out / "index.html").read_text(encoding="utf-8")


def test_build_rejects_bad_web_packages(tmp_path):
    p = _project(tmp_path, '[tool.pyxpo.web]\npackages = "pillow"\n')
    with pytest.raises(ConfigError):
        web.build(p)


def test_script_json_cannot_close_the_tag():
    assert "</" not in web._script_json({"x": "</script><script>alert(1)"})


def test_dev_server_spa_fallback_and_reload(tmp_path):
    p = _project(tmp_path)
    dev = web.DevServer(p, port=0, base="/demo")
    threading.Thread(target=dev.httpd.serve_forever, daemon=True).start()
    try:
        def get(path):
            with urllib.request.urlopen(dev.url.rstrip("/") + path if path else dev.url, timeout=5) as r:
                return r.headers.get("Content-Type"), r.read().decode("utf-8", "replace")
        assert dev.url.endswith("/demo/")
        ctype, js = get("/app.js")
        assert ctype.startswith("text/javascript") and "pyxpoPage" in js
        for route in ("", "/tool/info?x=1", "/../../etc/passwd", "/app.js/x"):
            ctype, html = get(route)
            assert ctype.startswith("text/html") and "PYXPO_CONFIG" in html and "/__pyxpo/reload" in html
        assert "location.reload()" in html and "keydown" in html  # R twice reloads, as in React Native
        bundle = _config(dev.root)["bundle"]
        assert get("/" + bundle)[0] == "application/zip"
        assert '<script src="/__pyxpo/devtools.js">' in get("")[1]
        with urllib.request.urlopen("http://%s:%d/__pyxpo/devtools.js" % dev.httpd.server_address[:2], timeout=5) as r:
            assert r.headers.get("Content-Type").startswith("text/javascript")
            assert b"PYXPO_DEVICE" in r.read()
    finally:
        dev.httpd.shutdown()
        dev.httpd.server_close()
    # the static build never carries the dev tools
    assert "devtools" not in (dev.root / "index.html").read_text(encoding="utf-8")
    assert not (dev.root / "devtools.js").exists()


def test_dev_server_without_devtools(tmp_path):
    dev = web.DevServer(_project(tmp_path), port=0, devtools=False)
    threading.Thread(target=dev.httpd.serve_forever, daemon=True).start()
    try:
        with urllib.request.urlopen(dev.url, timeout=5) as r:
            html = r.read().decode()
        assert "devtools" not in html and "/__pyxpo/reload" in html
        with urllib.request.urlopen(dev.url + "__pyxpo/devtools.js", timeout=5) as r:
            assert r.headers.get("Content-Type").startswith("text/html")  # SPA fallback, no script
    finally:
        dev.httpd.shutdown()
        dev.httpd.server_close()


def test_autolink_validates_web_section():
    base = {"name": "ok", "native": "X"}
    autolink.validate(dict(base, web={"packages": ["pillow"]}), "f")
    for bad in ([], {"packages": "pillow"}, {"packages": [""]}, {"packages": [1]}):
        with pytest.raises(BuildError):
            autolink.validate(dict(base, web=bad), "f")


# -- in-browser renderer --------------------------------------------------------------------------------------------
class Page:
    def __init__(self):
        self.got = []

    def receive(self, s):
        self.got.append(json.loads(s))


class FakeBackend:
    @staticmethod
    def call(method, args):
        if method == "boom":
            raise ValueError("bad input")
        if method == "slow":
            async def later():
                await asyncio.sleep(0)
                return {"twice": args[0] * 2}
            return later()
        return {"echo": args}


def test_browser_renderer_ops_and_module_calls(monkeypatch):
    monkeypatch.setattr(browser, "_mods", {"Demo": FakeBackend})

    async def go():
        ch, page = LocalChannel(), Page()
        r = browser.BrowserRenderer(ch, page, asyncio.get_running_loop())
        events = []
        ch.set_event_handler(lambda s: events.append(json.loads(s)))
        r.apply_json(json.dumps([
            {"op": "create", "id": 2, "type": "View", "props": {}},
            {"op": "call", "id": 5, "module": "History", "method": "sync", "args": ["/a", None]},
            {"op": "call", "id": 6, "module": "Demo", "method": "echo", "args": [1], "reply": True},
            {"op": "call", "id": 7, "module": "Demo", "method": "slow", "args": [4], "reply": True},
            {"op": "call", "id": 8, "module": "Demo", "method": "boom", "args": [], "reply": True},
            {"op": "call", "id": 9, "module": "Missing", "method": "x", "args": [], "reply": True},
            {"op": "call", "id": 10, "module": "Demo", "method": "echo", "args": []},
        ]))
        for _ in range(5):
            await asyncio.sleep(0)
        return page, events

    page, events = asyncio.run(go())
    sent = [o for m in page.got for o in m.get("ops", [])]
    assert [o["op"] for o in sent] == ["create", "call"] and sent[1]["module"] == "History"
    results = {e["id"]: e["payload"] for e in events}
    assert results[6] == {"value": {"echo": [1]}}
    assert results[7] == {"value": {"twice": 8}}
    assert results[8] == {"error": "bad input"}
    assert "not available on web" in results[9]["error"]
    assert 10 not in results  # no reply asked


def test_boot_reports_linked_modules(monkeypatch):
    monkeypatch.setattr(browser, "_mods", {"ImagePicker": object()})
    ran = []
    monkeypatch.setattr("pyxpo.router.entry.main", lambda: ran.append(1))
    monkeypatch.delenv("PYXPO_TARGET", raising=False)
    monkeypatch.delenv("PYXPO_ENV", raising=False)
    browser.boot(json.dumps({"os": "web", "window": {"width": 400, "height": 800}}))
    env = json.loads(os.environ["PYXPO_ENV"])
    assert os.environ["PYXPO_TARGET"] == "web" and ran == [1]
    assert env["modules"] == ["ImagePicker"] and env["window"]["width"] == 400

    old = dict(_env.current._data)
    try:
        _env.current._data.update(os="web", modules=env["modules"])
        modules.require_linked("ImagePicker", "image-picker")
        with pytest.raises(modules.ModuleNotLinkedError):
            modules.require_linked("Share", "sharing")
    finally:
        _env.current._data.clear()
        _env.current._data.update(old)


def test_cli_run_and_build_web(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(web, "build", lambda project, release=False, base=None: calls.append(("build", base)))
    monkeypatch.setattr(web, "serve", lambda project, port=8000, base=None, open_browser=True, devtools=True:
                        calls.append(("serve", port, base, open_browser, devtools)))
    p = _project(tmp_path)
    assert cli.main(["build", "web", "--dir", str(p), "--base", "/x"]) == 0
    assert cli.main(["run", "web", "--dir", str(p), "--port", "9001", "--no-open"]) == 0
    assert cli.main(["run", "web", "--dir", str(p), "--no-devtools"]) == 0
    assert calls == [("build", "/x"), ("serve", 9001, None, False, True), ("serve", 8000, None, True, False)]


def test_cli_web_build_error_is_printed(tmp_path, capsys):
    p = _project(tmp_path, '[tool.pyxpo.web]\nbase = "https://x.example"\n')
    assert cli.main(["build", "web", "--dir", str(p)]) == 1
    assert "plain path" in capsys.readouterr().err


def test_watch_stamp_sees_linked_module_packages(tmp_path):
    # A local editable module package (e.g. ../pyxpo-packages/pyxpo-whiteboard) is bundled into the web build, so editing it rebuilds.
    from pyxpo.build.web import _watch_stamp

    pkg = tmp_path / "pyxpo_demo"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("X = 1\n")
    (tmp_path / "app").mkdir()
    before = _watch_stamp(tmp_path, [pkg])
    assert _watch_stamp(tmp_path, [pkg]) == before
    (pkg / "__init__.py").write_text("X = 22\n")
    assert _watch_stamp(tmp_path, [pkg]) != before


def test_boot_loads_pyodide_builds_without_micropip():
    # micropip costs seconds to load, and numpy installed through it imported ~7x slower: Pyodide's own builds load
    # with loadPyodide/loadPackage, and only names missing from its lock file (or version specs) go to micropip.
    from pathlib import Path
    boot = (Path(__file__).resolve().parents[1] / "src" / "pyxpo" / "renderers" / "web" / "boot.js").read_text()
    assert 'fetch(cfg.pyodide + "pyodide-lock.json")' in boot
    assert "loadPyodide({ indexURL: cfg.pyodide, packages: builtin.known })" in boot
    assert 'micropip").install(builtin.other)' in boot and 'install(cfg.packages)' not in boot
