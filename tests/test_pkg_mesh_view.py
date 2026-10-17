"""pyxpo-mesh-view: props on the wire, events, seek over a fake bridge, the PXMESH1 writer and the web build."""
import json
import shutil
import struct
import subprocess

import pytest

from pyxpo import LocalChannel, component, create_app, use_ref
from pyxpo.app import App
from pyxpo.build import web
from pyxpo.module_testing import FakeBridge
from pyxpo.renderers.mock import MockRenderer
from pyxpo.renderers.web import page_js

import pyxpo_mesh_view as MV

UV = [(0, 0), (1, 0), (1, 1), (0, 1)]
ORDERS = [[0, 1, 2, 0, 2, 3]]


def mount(root, **props):
    ch = LocalChannel()
    r = MockRenderer(ch)
    app = create_app(root, ch, **props)
    return app, r


def test_props_on_the_wire_and_events():
    got = []

    @component
    def Root():
        return MV.MeshView(source="/c/a.pxmesh", texture="file:///c/my%20drawing.png", speed=2, loop=False,
                           background_color="#fff", on_load=got.append, on_error=got.append,
                           on_end=lambda e: got.append("end"), style={"flex": 1})

    app, r = mount(Root)
    (node,) = r.find_all("PxMeshView")
    p = node.props
    assert p["source"] == "/c/a.pxmesh" and p["texture"] == "/c/my drawing.png"
    assert p["playing"] is True and p["loop"] is False and p["speed"] == 2.0 and p["background_color"] == 0xFFFFFFFF
    assert p["on_load"] is True and p["on_error"] is True and p["on_end"] is True
    info = {"frames": 30, "fps": 30.0, "vertices": 4, "triangles": 2}
    r.emit("load", node, {"value": info})
    r.emit("error", node, {"value": {"message": "bad"}})
    r.emit("end", node, {"value": None})
    assert got == [info, {"message": "bad"}, "end"]


def test_defaults():
    @component
    def Root():
        return MV.MeshView()

    app, r = mount(Root)
    (node,) = r.find_all("PxMeshView")
    p = node.props
    assert p["source"] is None and p["texture"] is None and p["background_color"] == 0
    assert p["playing"] is True and p["loop"] is True and p["speed"] == 1.0
    assert not {"on_load", "on_error", "on_end"} & set(p)


@pytest.mark.parametrize("kw", [{"speed": -1}, {"speed": 17}, {"speed": True}, {"speed": float("nan")},
                                {"source": "https://x/a.pxmesh"}, {"texture": "file://host/a.png"}, {"source": ""}])
def test_bad_props(kw):
    @component
    def Root():
        return MV.MeshView(**kw)

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
        return MV.MeshView(ref=ref)

    app, r = mount(Root)
    return refs[-1], r.find_all("PxMeshView")[0].id


def test_seek():
    ref, tag = _handle()
    with FakeBridge("ios"):
        with pytest.raises(Exception, match="pyxpo-mesh-view"):
            ref.current.seek(0)
    with FakeBridge("android") as fb:
        fb.on("MeshView", "seek", lambda t, f: None)
        assert isinstance(ref.current, MV.MeshViewHandle)
        ref.current.seek(12)
        assert fb.calls[-1][:3] == ("MeshView", "seek", (tag, 12))
        for bad in (-1, 1.5, True):
            with pytest.raises(ValueError):
                ref.current.seek(bad)


def test_write_mesh_layout():
    frames = [[(10 + x * 20 + k, 5 + y * 40) for x, y in UV] for k in range(3)]   # 3 frames, x moves by 1
    data = MV.write_mesh(UV, frames, ORDERS + [[0, 2, 3]], order_of_frame=[0, 1, 0], fps=24)
    head = MV.read_header(data)
    assert head == {"vertices": 4, "frames": 3, "indices": 6, "orders": 2, "fps": 24.0,
                    "aspect": pytest.approx(22 / 40)}
    at = MV.HEADER_SIZE
    assert struct.unpack_from("<8f", data, at) == (0, 0, 1, 0, 1, 1, 0, 1)
    at += 4 * 8
    first = struct.unpack_from("<8f", data, at)
    assert first == pytest.approx((0, 0, 20 / 22, 0, 20 / 22, 1, 0, 1))      # box: x 10-32, y 5-45
    at += 3 * 4 * 8
    assert struct.unpack_from("<3H", data, at) == (0, 1, 0)
    at += 8                                          # 6 bytes, padded to 8
    assert struct.unpack_from("<12H", data, at) == (0, 1, 2, 0, 2, 3, 0, 2, 3, 0, 0, 0)
    assert at + 24 == len(data)


@pytest.mark.parametrize("args", [
    ([], [[]], ORDERS), (UV, [UV[:3]], ORDERS), (UV, [UV], []), (UV, [UV], [[0, 1]]), (UV, [UV], [[0, 1, 4]]),
])
def test_write_mesh_validates(args):
    with pytest.raises(ValueError):
        MV.write_mesh(*args)
    with pytest.raises(ValueError):
        MV.write_mesh(UV, [UV], ORDERS, order_of_frame=[1])


def test_read_header_checks():
    good = MV.write_mesh(UV, [UV, UV], ORDERS)
    assert MV.read_header(good)["frames"] == 2
    for bad in (b"", b"NOTAMESH" + good[8:], good[:-2], good + b"\0\0",
                good[:8] + struct.pack("<I", 0) + good[12:], good[:24] + struct.pack("<f", 0) + good[28:]):
        with pytest.raises(ValueError):
            MV.read_header(bad)


def test_numpy_input():
    np = pytest.importorskip("numpy")
    uv = np.array(UV, dtype=np.float32)
    frames = np.stack([uv * 3, uv * 3 + 1])
    assert MV.write_mesh(uv, frames, np.array(ORDERS, dtype=np.uint16)) == MV.write_mesh(UV, frames.tolist(), ORDERS)


def test_page_js_and_web_build(tmp_path):
    assert set(page_js({"MeshView": "pyxpo_mesh_view"})) == {"MeshView"}
    p = tmp_path / "proj"
    (p / "app").mkdir(parents=True)
    (p / "app" / "index.py").write_text("print('hi')\n")
    (p / "pyproject.toml").write_text('[project]\nname="x"\nversion="1.0.0"\n[tool.pyxpo]\nname = "Demo"\n'
                                      'bundle_id = "com.acme.demo"\nmodules = ["mesh-view"]\n')
    out = web.build(p)
    html = (out / "index.html").read_text(encoding="utf-8")
    cfg = json.loads(html.split("window.PYXPO_CONFIG = ", 1)[1].split(";</script>", 1)[0])
    assert cfg["scripts"] == ["modules/MeshView.js"]
    assert (out / "modules" / "MeshView.js").read_text() == open(MV.__path__[0] + "/web.js").read()


NODE_PARSE = r"""
const fs = require("fs");
let view, mod;
global.pyxpoPage = { defineView(t, f) { view = f; }, defineModule(n, f) { mod = f; } };
eval(fs.readFileSync(process.argv[2], "utf8"));
const parse = view.parse;
const b = fs.readFileSync(process.argv[3]);
const m = parse(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength));
console.log(JSON.stringify({v: m.vertices, f: m.frames, n: m.indexCount, fps: m.fps, of: Array.from(m.orderOfFrame),
  idx: Array.from(m.indices), pos1: Array.from(m.pos.slice(8, 10))}));
try { parse(new ArrayBuffer(40)); } catch (e) { console.log(e.message); }
"""


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_web_js_parses_files(tmp_path):
    subprocess.run(["node", "--check", MV.__path__[0] + "/web.js"], check=True)
    f = tmp_path / "a.pxmesh"
    f.write_bytes(MV.write_mesh(UV, [UV, [(x + 1, y) for x, y in UV], UV], ORDERS + [[3, 2, 0]], [0, 1, 1], fps=12))
    (tmp_path / "t.js").write_text(NODE_PARSE)
    out = subprocess.run(["node", str(tmp_path / "t.js"), MV.__path__[0] + "/web.js", str(f)], check=True,
                         capture_output=True, text=True).stdout.splitlines()
    got = json.loads(out[0])
    assert got == {"v": 4, "f": 3, "n": 6, "fps": 12, "of": [0, 1, 1], "idx": [0, 1, 2, 0, 2, 3, 3, 2, 0, 0, 0, 0],
                   "pos1": [0.5, 0]}
    assert out[1] == "not a PXMESH1 file"
