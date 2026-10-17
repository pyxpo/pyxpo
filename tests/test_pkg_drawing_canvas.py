"""pyxpo-drawing-canvas: props on the wire, handle calls over a fake bridge, web image files and the web build."""
import asyncio
import base64
import json
import shutil
import subprocess

import pytest

from pyxpo import LocalChannel, component, create_app, use_ref
from pyxpo.app import App
from pyxpo.build import web
from pyxpo.module_testing import FakeBridge
from pyxpo.renderers.mock import MockRenderer
from pyxpo.renderers.web import page_js

import pyxpo_drawing_canvas as DC

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode()


def run(coro):
    return asyncio.run(coro)


def mount(root, **props):
    ch = LocalChannel()
    r = MockRenderer(ch)
    app = create_app(root, ch, **props)
    return app, r


def test_props_on_the_wire_and_change_event():
    got = []

    @component
    def Root():
        return DC.DrawingCanvas(stroke_color="#ff0000", stroke_width=6, tool="eraser", on_change=got.append,
                                style={"flex": 1})

    app, r = mount(Root)
    (node,) = r.find_all("PxDrawingCanvas")
    p = node.props
    assert p["stroke_color"] == 0xFFFF0000 and p["stroke_width"] == 6.0 and p["tool"] == "eraser"
    assert p["background_color"] == 0xFFFFFFFF and p["enabled"] is True and p["on_change"] is True
    state = {"stroke_count": 1, "can_undo": True, "can_redo": False}
    r.emit("change", node, {"value": state})
    assert got == [state]


def test_defaults_have_no_change_handler():
    @component
    def Root():
        return DC.DrawingCanvas()

    app, r = mount(Root)
    (node,) = r.find_all("PxDrawingCanvas")
    assert "on_change" not in node.props and node.props["stroke_color"] == 0xFF000000


@pytest.mark.parametrize("kw", [{"tool": "brush"}, {"stroke_width": 0}, {"stroke_width": 501},
                                {"stroke_width": True}, {"stroke_width": float("nan")}])
def test_bad_props(kw):
    @component
    def Root():
        return DC.DrawingCanvas(**kw)

    app = App(Root, LocalChannel(), None)
    app.on_error = lambda e: (_ for _ in ()).throw(e)
    with pytest.raises(ValueError):
        app.start()


def _handle():
    refs = []

    @component
    def Root():
        ref = use_ref(None)
        refs.append(ref)
        return DC.DrawingCanvas(ref=ref)

    app, r = mount(Root)
    return refs[-1], r.find_all("PxDrawingCanvas")[0].id


def test_not_linked():
    ref, _ = _handle()
    with FakeBridge("ios"):
        with pytest.raises(Exception, match="pyxpo-drawing-canvas"):
            ref.current.undo()


def test_handle_methods():
    ref, tag = _handle()  # the app sets the desktop env, so the fake bridge comes after
    strokes = [{"tool": "pen", "color": 0xFF112233, "width": 4.0, "points": [1.0, 2.0, 3.0, 4.0]}]
    with FakeBridge("android") as fb:
        for m in ("undo", "redo", "clear"):
            fb.on("DrawingCanvas", m, lambda t: None)
        fb.on("DrawingCanvas", "getStrokes", lambda t: strokes)
        fb.on("DrawingCanvas", "setStrokes", lambda t, s: None)
        fb.on("DrawingCanvas", "toImage", lambda t, o: {"uri": "file:///d.png", "width": 10, "height": 8,
                                                         "x": 0, "y": 0})
        c = ref.current
        assert isinstance(c, DC.DrawingCanvasHandle)
        c.undo()
        c.redo()
        c.clear()
        assert [x[:3] for x in fb.calls[-3:]] == [("DrawingCanvas", "undo", (tag,)), ("DrawingCanvas", "redo", (tag,)),
                                                  ("DrawingCanvas", "clear", (tag,))]
        assert run(c.get_strokes_async()) == strokes
        run(c.setStrokesAsync([{"color": "#00ff00", "points": [5, 6]}]))
        assert fb.calls[-1] == ("DrawingCanvas", "setStrokes",
                                (tag, [{"tool": "pen", "color": 0xFF00FF00, "width": 4.0, "points": [5.0, 6.0]}]))
        assert run(c.to_image_async(trim=True, padding=8, scale=2))["uri"] == "file:///d.png"
        assert fb.calls[-1] == ("DrawingCanvas", "toImage", (tag, {"format": "png", "trim": True, "padding": 8.0,
                                                                  "background": True, "quality": 1.0, "scale": 2.0}))
        fb.on("DrawingCanvas", "toImage", lambda t, o: None)
        assert run(c.toImageAsync(format="jpg", trim=True)) is None


@pytest.mark.parametrize("strokes", ["x", [1], [{"points": [1]}], [{"points": []}], [{"points": [1, "a"]}],
                                     [{"tool": "brush", "points": [1, 2]}], [{"width": 0, "points": [1, 2]}]])
def test_set_strokes_validates(strokes):
    ref, _ = _handle()
    with FakeBridge("ios") as fb:
        fb.on("DrawingCanvas", "setStrokes", lambda t, s: None)
        with pytest.raises((ValueError, TypeError)):
            run(ref.current.set_strokes_async(strokes))


@pytest.mark.parametrize("kw", [{"format": "gif"}, {"padding": -1}, {"quality": 2}, {"scale": 0}, {"scale": 9}])
def test_to_image_validates(kw):
    ref, _ = _handle()
    with FakeBridge("ios") as fb:
        fb.on("DrawingCanvas", "toImage", lambda t, o: None)
        with pytest.raises(ValueError):
            run(ref.current.to_image_async(**kw))


def test_web_image_is_written_to_a_file(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    res = DC._save({"base64": PNG, "width": 3, "height": 2, "x": 1.5, "y": 0}, "png")
    assert "base64" not in res and res["width"] == 3 and res["x"] == 1.5
    path = res["uri"][len("file://"):]
    assert path.startswith(str(tmp_path / "pyxpo" / "drawing-canvas")) and path.endswith(".png")
    assert open(path, "rb").read() == base64.b64decode(PNG)
    native = {"uri": "file:///x.png", "width": 1, "height": 1, "x": 0, "y": 0}
    assert DC._save(dict(native), "png") == native


def test_page_js_and_web_build(tmp_path):
    assert set(page_js({"DrawingCanvas": "pyxpo_drawing_canvas"})) == {"DrawingCanvas"}
    p = tmp_path / "proj"
    (p / "app").mkdir(parents=True)
    (p / "app" / "index.py").write_text("print('hi')\n")
    (p / "pyproject.toml").write_text('[project]\nname="x"\nversion="1.0.0"\n[tool.pyxpo]\nname = "Demo"\n'
                                      'bundle_id = "com.acme.demo"\nmodules = ["drawing-canvas"]\n')
    out = web.build(p)
    html = (out / "index.html").read_text(encoding="utf-8")
    cfg = json.loads(html.split("window.PYXPO_CONFIG = ", 1)[1].split(";</script>", 1)[0])
    assert cfg["scripts"] == ["modules/DrawingCanvas.js"]
    assert (out / "modules" / "DrawingCanvas.js").read_text() == open(DC.__path__[0] + "/web.js").read()


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_web_js_parses():
    subprocess.run(["node", "--check", DC.__path__[0] + "/web.js"], check=True)
