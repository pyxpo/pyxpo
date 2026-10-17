"""pyxpo-whiteboard: props on the wire, the board hook and toolbar, handle calls over a fake bridge, geometry
helpers, web image files and the web build."""
import asyncio
import base64
import json
import math
import shutil
import subprocess

import pytest

from pyxpo import LocalChannel, View, component, create_app, use_ref
from pyxpo.app import App
from pyxpo.build import web
from pyxpo.module_testing import FakeBridge
from pyxpo.renderers.mock import MockRenderer
from pyxpo.renderers.web import page_js

import pyxpo_whiteboard as WB

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode()


def run(coro):
    return asyncio.run(coro)


def mount(root, **props):
    ch = LocalChannel()
    r = MockRenderer(ch)
    app = create_app(root, ch, **props)
    return app, r


def by_id(r, tid):
    for n in r.root.walk():
        if n.props.get("test_id") == tid or n.props.get("testID") == tid:
            return n
    raise AssertionError("no node with test id %r" % tid)


def test_props_on_the_wire_and_events():
    got, starts = [], []

    @component
    def Root():
        return WB.Whiteboard(tool="rect", color="#ff0000", width=6, opacity=0.5, fill_color="#00ff00",
                             fill_tolerance=40.4, on_change=got.append, on_draw_start=starts.append,
                             style={"flex": 1})

    app, r = mount(Root)
    (node,) = r.find_all("PxWhiteboard")
    p = node.props
    assert p["tool"] == "rect" and p["width"] == 6.0 and p["fill_tolerance"] == 40
    assert p["color"] == 0x80FF0000 and p["fill_color"] == 0x8000FF00
    assert p["background_color"] == 0xFFFFFFFF and p["enabled"] is True
    assert p["on_change"] is True and p["on_draw_start"] is True
    state = {"element_count": 1, "can_undo": True, "can_redo": False}
    r.emit("change", node, {"value": state})
    r.emit("draw_start", node, {"value": {"tool": "rect"}})
    assert got == [state] and starts == [{"tool": "rect"}]


def test_defaults_and_marker_alpha():
    @component
    def Root():
        return View(WB.Whiteboard(), WB.Whiteboard(tool="marker", color="#112233"))

    app, r = mount(Root)
    a, b = r.find_all("PxWhiteboard")
    assert "on_change" not in a.props and "on_draw_start" not in a.props
    assert a.props["color"] == 0xFF000000 and a.props["fill_color"] == 0 and a.props["fill_tolerance"] == 32
    assert b.props["color"] == (round(255 * WB.MARKER_ALPHA) << 24) | 0x112233


@pytest.mark.parametrize("kw", [{"tool": "brush"}, {"width": 0}, {"width": 501}, {"width": True},
                                {"width": float("nan")}, {"opacity": 0}, {"opacity": 1.5},
                                {"fill_tolerance": 300}, {"color": "nope"}])
def test_bad_props(kw):
    @component
    def Root():
        return WB.Whiteboard(**kw)

    app = App(Root, LocalChannel(), None)
    app.on_error = lambda e: (_ for _ in ()).throw(e)
    with pytest.raises(ValueError):
        app.start()


def _board_app(**hook):
    boards = []

    @component
    def Root():
        b = WB.use_whiteboard(**hook)
        boards.append(b)
        return View(WB.Whiteboard(board=b, style={"flex": 1}), WB.WhiteboardToolbar(board=b))

    app, r = mount(Root)
    return boards, r


def test_board_drives_the_view_and_toolbar():
    boards, r = _board_app(color="#2F6FE4", width=8)
    b = boards[-1]
    assert b.is_empty and b.tool == "pen" and not b.can_undo
    node = r.find_all("PxWhiteboard")[0]
    assert node.props["color"] == 0xFF2F6FE4 and node.props["width"] == 8.0
    assert by_id(r, "wb-tool-pen").props["accessibility_state"]["selected"] is True
    assert by_id(r, "wb-undo").props["accessibility_state"]["disabled"] is True

    # A touch starts: the hint can hide before the first element lands.
    r.emit("draw_start", node, {"value": {"tool": "pen"}})
    assert not boards[-1].is_empty and boards[-1].drawing
    r.emit("change", node, {"value": {"element_count": 1, "can_undo": True, "can_redo": False}})
    b = boards[-1]
    assert not b.drawing and b.element_count == 1 and not b.is_empty
    assert by_id(r, "wb-undo").props["accessibility_state"]["disabled"] is False

    r.press(by_id(r, "wb-shape-star"))
    assert boards[-1].tool == "star" and node.props["tool"] == "star"
    r.press(by_id(r, "wb-fill-shapes"))
    assert boards[-1].fill_shapes and node.props["fill_color"] == 0xFF2F6FE4
    r.press(by_id(r, "wb-color-3"))
    assert node.props["color"] == 0xFFE5322D and boards[-1].color == WB.PALETTE[3]
    r.press(by_id(r, "wb-width-24"))
    assert node.props["width"] == 24.0
    r.press(by_id(r, "wb-tool-eraser"))
    assert boards[-1].tool == "eraser"
    with pytest.raises(AssertionError):
        by_id(r, "wb-opacity")  # no opacity for the eraser
    r.press(by_id(r, "wb-color-0"))
    assert boards[-1].tool == "pen"  # a color goes back to the pen


def test_opacity_slider():
    boards, r = _board_app()
    r.emit("value_change", by_id(r, "wb-opacity"), {"value": 0.25})
    assert boards[-1].opacity == 0.25
    assert r.find_all("PxWhiteboard")[0].props["color"] == (round(255 * 0.25) << 24) | 0x1F1A24
    assert "25%" in r.texts()


@pytest.mark.parametrize("call", [lambda b: b.set_tool("brush"), lambda b: b.set_width(0),
                                  lambda b: b.set_opacity(2), lambda b: b.set_color("nope")])
def test_board_setters_validate(call):
    boards, _ = _board_app()
    with pytest.raises(ValueError):
        call(boards[-1])


def test_board_methods_go_to_the_view():
    boards, r = _board_app()
    tag = r.find_all("PxWhiteboard")[0].id
    with FakeBridge("ios") as fb:
        for m in ("undo", "redo", "clear"):
            fb.on("Whiteboard", m, lambda t: None)
        fb.on("Whiteboard", "getElements", lambda t: [])
        b = boards[-1]
        b.undo()
        b.redo()
        b.clear()
        assert [c[:3] for c in fb.calls[-3:]] == [("Whiteboard", m, (tag,)) for m in ("undo", "redo", "clear")]
        assert run(b.get_elements_async()) == []


def _handle():
    refs = []

    @component
    def Root():
        ref = use_ref(None)
        refs.append(ref)
        return WB.Whiteboard(ref=ref)

    app, r = mount(Root)
    return refs[-1], r.find_all("PxWhiteboard")[0].id


def test_not_linked():
    ref, _ = _handle()
    with FakeBridge("ios"):
        with pytest.raises(Exception, match="pyxpo-whiteboard"):
            ref.current.undo()


def test_handle_methods():
    ref, tag = _handle()
    elements = [{"type": "fill", "x": 3.0, "y": 4.0, "color": 0xFF112233}]
    with FakeBridge("android") as fb:
        fb.on("Whiteboard", "getElements", lambda t: elements)
        fb.on("Whiteboard", "setElements", lambda t, s: None)
        fb.on("Whiteboard", "toImage", lambda t, o: {"uri": "file:///d.png", "width": 10, "height": 8,
                                                      "x": 0, "y": 0})
        h = ref.current
        assert isinstance(h, WB.WhiteboardHandle)
        assert run(h.getElementsAsync()) == elements
        run(h.set_elements_async([
            {"color": "#00ff00", "points": [5, 6]},
            {"type": "shape", "shape": "ellipse", "x0": 0, "y0": 0, "x1": 10, "y1": 5, "fill": "#ff0000"},
            {"type": "fill", "x": 1, "y": 2},
        ]))
        assert fb.calls[-1] == ("Whiteboard", "setElements", (tag, [
            {"type": "stroke", "tool": "pen", "color": 0xFF00FF00, "width": 4.0, "points": [5.0, 6.0]},
            {"type": "shape", "shape": "ellipse", "color": 0xFF000000, "width": 4.0, "fill": 0xFFFF0000,
             "x0": 0.0, "y0": 0.0, "x1": 10.0, "y1": 5.0},
            {"type": "fill", "x": 1.0, "y": 2.0, "color": 0xFF000000},
        ]))
        assert run(h.to_image_async(trim=True, padding=8, scale=2))["uri"] == "file:///d.png"
        assert fb.calls[-1] == ("Whiteboard", "toImage", (tag, {"format": "png", "trim": True, "padding": 8.0,
                                                                "background": True, "quality": 1.0, "scale": 2.0}))
        fb.on("Whiteboard", "toImage", lambda t, o: None)
        assert run(h.toImageAsync(format="jpg", trim=True)) is None


@pytest.mark.parametrize("elements", [
    "x", [1], [{"points": [1]}], [{"points": []}], [{"points": [1, "a"]}], [{"tool": "brush", "points": [1, 2]}],
    [{"width": 0, "points": [1, 2]}], [{"type": "blob"}], [{"type": "shape", "shape": "blob", "x0": 0, "y0": 0,
                                                             "x1": 1, "y1": 1}],
    [{"type": "shape", "shape": "rect", "x0": 0, "y0": 0, "x1": 1}], [{"type": "fill", "x": 1}],
    [{"type": "fill", "x": 1, "y": 1, "color": True}],
])
def test_set_elements_validates(elements):
    ref, _ = _handle()
    with FakeBridge("ios") as fb:
        fb.on("Whiteboard", "setElements", lambda t, s: None)
        with pytest.raises((ValueError, TypeError)):
            run(ref.current.set_elements_async(elements))


@pytest.mark.parametrize("kw", [{"format": "gif"}, {"padding": -1}, {"quality": 2}, {"scale": 0}, {"scale": 9}])
def test_to_image_validates(kw):
    ref, _ = _handle()
    with FakeBridge("ios") as fb:
        fb.on("Whiteboard", "toImage", lambda t, o: None)
        with pytest.raises(ValueError):
            run(ref.current.to_image_async(**kw))


# ---------------------------------------------------------------- geometry

def test_shape_outlines():
    (rect,) = WB.shape_outline("rect", 10, 20, 0, 0)
    assert rect == [0, 0, 10, 0, 10, 20, 0, 20, 0, 0]
    (tri,) = WB.shape_outline("triangle", 0, 0, 10, 20)
    assert tri == [5, 0, 10, 20, 0, 20, 5, 0]
    (star,) = WB.shape_outline("star", 0, 0, 10, 10)
    assert len(star) == 22 and star[:2] == [5.0, 0.0] and star[-2:] == star[:2]
    (ell,) = WB.shape_outline("ellipse", 0, 0, 20, 10, segments=8)
    assert len(ell) == 18 and ell[:2] == [20.0, 5.0]
    line, h1, h2 = WB.shape_outline("arrow", 0, 0, 100, 0, width=4)
    assert line == [0, 0, 100, 0] and h1[:2] == [100, 0] and h2[:2] == [100, 0]
    assert math.hypot(h1[2] - 100, h1[3]) == pytest.approx(14)  # 3.5 x width
    assert h1[2] < 100 and h1[3] == pytest.approx(-h2[3])
    _, short, _ = WB.shape_outline("arrow", 0, 0, 10, 0, width=4)
    assert math.hypot(short[2] - 10, short[3]) == pytest.approx(5)  # at most half the shaft
    with pytest.raises(ValueError):
        WB.shape_outline("blob", 0, 0, 1, 1)


def test_new_shape_outlines():
    (dia,) = WB.shape_outline("diamond", 0, 0, 10, 20)
    assert dia[:8] == [5, 0, 10, 10, 5, 20, 0, 10] and dia[-2:] == dia[:2]
    (hexa,) = WB.shape_outline("hexagon", 0, 0, 20, 20)
    assert len(hexa) == 14 and hexa[:2] == pytest.approx([10, 0]) and hexa[-2:] == hexa[:2]
    assert all(math.hypot(x - 10, y - 10) == pytest.approx(10) for x, y in zip(hexa[::2], hexa[1::2]))
    (heart,) = WB.shape_outline("heart", 0, 0, 32, 29)
    xs, ys = heart[::2], heart[1::2]
    assert min(xs) == pytest.approx(0, abs=0.1) and max(xs) == pytest.approx(32, abs=0.1)
    assert min(ys) >= 0 and max(ys) == pytest.approx(29)
    assert heart[:2] == pytest.approx([16, 7])  # the dip at the top middle


# ---------------------------------------------------------------- dashes, pattern, picker

def test_dash_on_elements():
    ref, _ = _handle()
    with FakeBridge("ios") as fb:
        fb.on("Whiteboard", "setElements", lambda t, s: None)
        run(ref.current.set_elements_async([
            {"points": [1, 2], "dash": True}, {"tool": "eraser", "points": [1, 2], "dash": True},
            {"type": "shape", "shape": "heart", "x0": 0, "y0": 0, "x1": 1, "y1": 1, "dash": 1},
            {"type": "shape", "shape": "rect", "x0": 0, "y0": 0, "x1": 1, "y1": 1}]))
        sent = fb.calls[-1][2][1]
    sent = json.loads(sent) if isinstance(sent, str) else sent
    assert sent[0]["dash"] is True and "dash" not in sent[1]
    assert sent[2]["dash"] is True and "dash" not in sent[3]


def test_dash_and_pattern_on_the_wire():
    @component
    def Root():
        return View(WB.Whiteboard(dash=True, pattern="grid", pattern_color="#ff0000"),
                    WB.Whiteboard(tool="eraser", dash=True))

    app, r = mount(Root)
    a, b = r.find_all("PxWhiteboard")
    assert a.props["dash"] is True and a.props["pattern"] == "grid" and a.props["pattern_color"] == 0xFFFF0000
    assert b.props["dash"] is False and b.props["pattern"] == "none" and b.props["pattern_color"] == WB.PATTERN_COLOR


def test_bad_pattern():
    @component
    def Root():
        return WB.Whiteboard(pattern="stripes")

    app = App(Root, LocalChannel(), None)
    app.on_error = lambda e: (_ for _ in ()).throw(e)
    with pytest.raises(ValueError):
        app.start()


def test_board_dash_and_pattern():
    boards, r = _board_app(dash=True, pattern="dots")
    node = r.find_all("PxWhiteboard")[0]
    assert node.props["dash"] is True and node.props["pattern"] == "dots"
    assert by_id(r, "wb-dash").props["accessibility_state"]["selected"] is True
    r.press(by_id(r, "wb-dash"))
    assert boards[-1].dash is False and node.props["dash"] is False
    r.press(by_id(r, "wb-pattern-lines"))
    assert boards[-1].pattern == "lines" and node.props["pattern"] == "lines"
    assert by_id(r, "wb-pattern-lines").props["accessibility_state"]["selected"] is True
    r.press(by_id(r, "wb-tool-eraser"))
    with pytest.raises(AssertionError):
        by_id(r, "wb-dash")  # no dashed eraser
    with pytest.raises(ValueError):
        boards[-1].set_pattern("stripes")


def test_picker_picks_a_color_and_goes_back():
    picks = []
    boards = []

    @component
    def Root():
        b = WB.use_whiteboard()
        boards.append(b)
        return View(WB.Whiteboard(board=b, on_pick=picks.append), WB.WhiteboardToolbar(board=b))

    app, r = mount(Root)
    r.press(by_id(r, "wb-shape-heart"))
    r.press(by_id(r, "wb-tool-picker"))
    node = r.find_all("PxWhiteboard")[0]
    assert boards[-1].tool == "picker" and node.props["tool"] == "picker" and node.props["on_pick"] is True
    r.emit("pick", node, {"value": {"color": 0xFF2F6FE4}})
    b = boards[-1]
    assert picks == [{"color": 0xFF2F6FE4}] and b.color == "#2F6FE4" and b.tool == "heart"
    assert node.props["color"] == 0xFF2F6FE4
    # A swatch while picking also goes back to the tool before the picker.
    r.press(by_id(r, "wb-tool-picker"))
    r.press(by_id(r, "wb-tool-picker"))  # twice: still remembers the heart
    r.press(by_id(r, "wb-color-0"))
    assert boards[-1].tool == "heart"


def test_color_grid():
    rows = WB.color_grid(hues=6, shades=3)
    assert len(rows) == 4 and all(len(r) == 6 for r in rows)
    assert rows[-1][0] == "#FFFFFF" and rows[-1][-1] == "#000000"
    assert all(len(c) == 7 and c[0] == "#" for r in rows for c in r)
    assert len(set(rows[0] + rows[1] + rows[2])) == 18
    assert len(WB.color_grid(1, 1)) == 2
    with pytest.raises(ValueError):
        WB.color_grid(0, 3)
    with pytest.raises(ValueError):
        WB.color_grid(3, 0)


def test_toolbar_spectrum_picks_from_the_grid():
    boards = []

    @component
    def Root():
        b = WB.use_whiteboard()
        boards.append(b)
        return View(WB.Whiteboard(board=b), WB.WhiteboardToolbar(board=b, spectrum=True, patterns=False))

    app, r = mount(Root)
    with pytest.raises(AssertionError):
        by_id(r, "wb-pattern-grid")
    want = WB.color_grid()[2][4]
    r.press(by_id(r, "wb-grid-2-4"))
    assert boards[-1].color == want
    assert by_id(r, "wb-grid-2-4").props["accessibility_state"]["selected"] is True
    assert r.find_all("PxWhiteboard")[0].props["color"] == 0xFF000000 | int(want[1:], 16)


def test_to_strokes_transform_and_bounds():
    els = [
        {"points": [0, 0, 10, 0], "color": 1, "width": 2},
        {"type": "stroke", "tool": "marker", "points": [5, 5], "color": 2, "width": 4},
        {"type": "stroke", "tool": "eraser", "points": [100, 100], "color": 3, "width": 50},
        {"type": "shape", "shape": "rect", "x0": 20, "y0": 20, "x1": 30, "y1": 40, "color": 4, "width": 2,
         "fill": 0},
        {"type": "fill", "x": 25, "y": 30, "color": 5},
    ]
    s = WB.to_strokes(els)
    assert [x["tool"] for x in s] == ["pen", "pen", "eraser", "pen"]
    assert s[3]["points"] == [20, 20, 30, 20, 30, 40, 20, 40, 20, 20]
    assert WB.bounds(els) == (-1.0, -1.0, 31.0, 41.0)  # the eraser and the fill do not count
    assert WB.bounds([]) is None and WB.bounds([els[4]]) is None
    t = WB.transform(els, 2, 1, -1)
    assert t[0]["points"] == [1, -1, 21, -1] and t[0]["width"] == 4.0
    assert (t[3]["x0"], t[3]["y0"], t[3]["x1"], t[3]["y1"], t[3]["width"]) == (41, 39, 61, 79, 4.0)
    assert (t[4]["x"], t[4]["y"]) == (51, 59)
    assert els[0]["points"] == [0, 0, 10, 0]  # input not changed


def test_icons_parse():
    from pyxpo.vector_icons import parse_path
    for name, d in WB.ICONS.items():
        assert parse_path(d), name


# ---------------------------------------------------------------- web

def test_web_image_is_written_to_a_file(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    res = WB._save({"base64": PNG, "width": 3, "height": 2, "x": 1.5, "y": 0}, "png")
    assert "base64" not in res and res["width"] == 3 and res["x"] == 1.5
    path = res["uri"][len("file://"):]
    assert path.startswith(str(tmp_path / "pyxpo" / "whiteboard")) and path.endswith(".png")
    assert open(path, "rb").read() == base64.b64decode(PNG)
    native = {"uri": "file:///x.png", "width": 1, "height": 1, "x": 0, "y": 0}
    assert WB._save(dict(native), "png") == native


def test_page_js_and_web_build(tmp_path):
    assert set(page_js({"Whiteboard": "pyxpo_whiteboard"})) == {"Whiteboard"}
    p = tmp_path / "proj"
    (p / "app").mkdir(parents=True)
    (p / "app" / "index.py").write_text("print('hi')\n")
    (p / "pyproject.toml").write_text('[project]\nname="x"\nversion="1.0.0"\n[tool.pyxpo]\nname = "Demo"\n'
                                      'bundle_id = "com.acme.demo"\nmodules = ["whiteboard"]\n')
    out = web.build(p)
    html = (out / "index.html").read_text(encoding="utf-8")
    cfg = json.loads(html.split("window.PYXPO_CONFIG = ", 1)[1].split(";</script>", 1)[0])
    assert cfg["scripts"] == ["modules/Whiteboard.js"]
    assert (out / "modules" / "Whiteboard.js").read_text() == open(WB.__path__[0] + "/web.js").read()


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_web_js_parses():
    subprocess.run(["node", "--check", WB.__path__[0] + "/web.js"], check=True)


def test_every_public_name_resolves():
    for name in WB.__all__:
        assert hasattr(WB, name), name
    assert WB.PATTERN_LABELS["grid"] == "Grid" and set(WB.PATTERN_LABELS) == set(WB.PATTERNS)
    assert set(WB.TOOL_LABELS) == set(WB.TOOLS)
