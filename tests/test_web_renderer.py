import asyncio
import json
import queue

import pytest

from pyxpo.channel import LocalChannel
from pyxpo.renderers.web import WebRenderer


def _ops(r, ops):
    r.apply_json(json.dumps(ops))


def test_snapshot_rebuilds_tree():
    r = WebRenderer(LocalChannel())
    _ops(r, [{"op": "create", "id": 2, "type": "View", "props": {"style": {"width": 10}}},
             {"op": "create", "id": 3, "type": "Text", "props": {"text": "hi"}},
             {"op": "insert", "parent": 1, "id": 2, "index": 0},
             {"op": "insert", "parent": 2, "id": 3, "index": 0}])
    snap = r.snapshot()
    assert [o["op"] for o in snap] == ["create", "create", "insert", "insert"]
    assert snap[2] == {"op": "insert", "parent": 1, "id": 2, "index": 0}
    assert snap[3] == {"op": "insert", "parent": 2, "id": 3, "index": 0}


def test_ops_are_broadcast_without_native_calls():
    r = WebRenderer(LocalChannel())
    q = queue.Queue()  # same put_nowait/get_nowait; an asyncio.Queue needs a loop on Python 3.9
    r.clients.append(q)
    _ops(r, [{"op": "create", "id": 2, "type": "View", "props": {}}, {"op": "mark"},
             {"op": "call", "id": 7, "module": "Scroll", "method": "to", "args": [2, 0, 0, True]}])
    msg = json.loads(q.get_nowait())
    assert [o["op"] for o in msg["ops"]] == ["create", "call"]


async def _request(port, raw):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(raw.encode())
    await writer.drain()
    status = (await reader.readline()).decode()
    writer.close()
    return int(status.split()[1])


def test_http_checks_host_and_token():
    async def main():
        r = WebRenderer(LocalChannel())
        task = asyncio.ensure_future(r.serve(open_window=False))
        while not r.port:
            await asyncio.sleep(0.01)
        p, t = r.port, r.token
        ok = await _request(p, "GET /?t=%s HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n\r\n" % (t, p))
        bad_token = await _request(p, "GET /?t=nope HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n\r\n" % p)
        bad_host = await _request(p, "GET /?t=%s HTTP/1.1\r\nHost: evil.test:%d\r\n\r\n" % (t, p))
        script = await _request(p, "GET /app.js HTTP/1.1\r\nHost: localhost:%d\r\n\r\n" % p)
        r.closed.set()
        await task
        return ok, bad_token, bad_host, script

    assert asyncio.run(main()) == (200, 403, 403, 200)


def test_image_manipulator_desktop_backend(tmp_path, monkeypatch):
    pil = pytest.importorskip("PIL.Image")
    from pyxpo_image_manipulator import desktop

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    src = tmp_path / "in.png"
    pil.new("RGBA", (40, 20), (255, 0, 0, 128)).save(src)
    assert desktop.call("info", [str(src)])["width"] == 40
    h = desktop.call("open", ["file://" + str(src), 0])["h"]
    out = desktop.call("render", [h, {"ops": [{"op": "rotate", "degrees": 90}], "format": "jpeg", "quality": 0.5}])
    assert (out["width"], out["height"], out["format"]) == (20, 40, "jpeg")
    assert pil.open(out["uri"]).size == (20, 40)
    desktop.call("close", [h])


def _page_pkg(tmp_path, monkeypatch, name="pxdemo_pagepkg"):
    d = tmp_path / name
    d.mkdir()
    (d / "__init__.py").write_text("")
    (d / "web.js").write_text("pyxpoPage.defineView('PxDemo', () => ({}));\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    return d


def test_page_js_finds_module_web_js(tmp_path, monkeypatch):
    from pyxpo.renderers.web import page_js
    d = _page_pkg(tmp_path, monkeypatch)
    assert page_js({"Demo": "pxdemo_pagepkg", "Gone": "pxdemo_not_installed", "Json": "json"}) == {"Demo": d / "web.js"}


def test_module_web_js_is_served_and_answers_calls_in_page(tmp_path, monkeypatch):
    from pyxpo.renderers.web import backends
    _page_pkg(tmp_path, monkeypatch)
    monkeypatch.setattr(backends, "_linked", lambda: {"Demo": "pxdemo_pagepkg"})

    async def main():
        r = WebRenderer(LocalChannel())
        assert "Demo" in r.js_calls and "Scroll" in r.js_calls
        task = asyncio.ensure_future(r.serve(open_window=False))
        while not r.port:
            await asyncio.sleep(0.01)
        p = r.port
        js = await _request(p, "GET /module/Demo.js HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n\r\n" % p)
        other = await _request(p, "GET /module/Other.js HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n\r\n" % p)
        r.closed.set()
        await task
        return js, other

    assert asyncio.run(main()) == (200, 403)


def test_pointer_events_reach_every_renderer():
    # An overlay with pointer_events="none" (a hint over a canvas) must let touches through on every target.
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "src" / "pyxpo"
    web = (src / "renderers" / "web" / "app.js").read_text()
    css = (src / "renderers" / "web" / "index.html").read_text()
    ios = (src / "templates" / "ios" / "gen" / "runtime" / "OpApplier.swift").read_text()
    ios_views = (src / "templates" / "ios" / "gen" / "runtime" / "PxViews.swift").read_text()
    kt = src / "templates" / "android" / "gen" / "runtime" / "java" / "dev" / "pyxpo" / "runtime"
    assert "p.pointer_events" in web and ".pe-none" in css and ".pe-box-none > *" in css
    assert 'case "pointer_events"' in ios and "override func hitTest" in ios_views
    assert '"pointer_events" ->' in (kt / "OpApplier.kt").read_text()
    assert 'pointerEvents != "none"' in (kt / "PxViews.kt").read_text()
