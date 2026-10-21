"""pyxpo-video: props on the wire, events, play/pause/seek over a fake bridge and the web build."""
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

import pyxpo_video as V


def mount(root, **props):
    ch = LocalChannel()
    r = MockRenderer(ch)
    app = create_app(root, ch, **props)
    return app, r


def test_props_on_the_wire_and_events():
    got = []

    @component
    def Root():
        return V.VideoView(source="file:///c/my%20reel.mp4", playing=False, loop=True, muted=True, controls=False,
                           resize_mode="cover", on_load=got.append, on_error=got.append,
                           on_end=lambda e: got.append("end"), style={"flex": 1})

    app, r = mount(Root)
    (node,) = r.find_all("PxVideoView")
    p = node.props
    assert p["source"] == "/c/my reel.mp4" and p["resize_mode"] == "cover"
    assert p["playing"] is False and p["loop"] is True and p["muted"] is True and p["controls"] is False
    assert p["on_load"] is True and p["on_error"] is True and p["on_end"] is True
    info = {"duration": 41.9, "width": 1080.0, "height": 1920.0}
    r.emit("load", node, {"value": info})
    r.emit("error", node, {"value": {"message": "bad"}})
    r.emit("end", node, {"value": None})
    assert got == [info, {"message": "bad"}, "end"]


def test_defaults_and_urls():
    @component
    def Root():
        return V.VideoView()

    app, r = mount(Root)
    p = r.find_all("PxVideoView")[0].props
    assert p["source"] is None and p["resize_mode"] == "contain"
    assert p["playing"] is True and p["loop"] is False and p["muted"] is False and p["controls"] is True
    assert not {"on_load", "on_error", "on_end"} & set(p)
    for src in ("/a/b.mp4", "https://x.test/a.mp4", "http://x.test/a.mp4"):
        assert V._source(src) == src


@pytest.mark.parametrize("kw", [{"source": ""}, {"source": "rtsp://x/a"}, {"source": "file://host/a.mp4"},
                                {"source": 3}, {"resize_mode": "fill"}])
def test_bad_props(kw):
    @component
    def Root():
        return V.VideoView(**kw)

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
        return V.VideoView(ref=ref, source="/a.mp4")

    app, r = mount(Root)
    return refs[-1], r.find_all("PxVideoView")[0].id


def test_play_pause_seek():
    ref, tag = _handle()
    with FakeBridge("ios"):
        with pytest.raises(Exception, match="pyxpo-video"):
            ref.current.play()
    with FakeBridge("android") as fb:
        for m in ("play", "pause", "seek"):
            fb.on("Video", m, lambda *a: None)
        assert isinstance(ref.current, V.VideoViewHandle)
        ref.current.play()
        ref.current.pause()
        ref.current.seek(2)
        assert [c[:3] for c in fb.calls[-3:]] == [("Video", "play", (tag,)), ("Video", "pause", (tag,)),
                                                  ("Video", "seek", (tag, 2.0))]
        for bad in (-1, True, float("inf"), "1"):
            with pytest.raises(ValueError):
                ref.current.seek(bad)


def test_page_js_and_web_build(tmp_path):
    assert set(page_js({"Video": "pyxpo_video"})) == {"Video"}
    p = tmp_path / "proj"
    (p / "app").mkdir(parents=True)
    (p / "app" / "index.py").write_text("print('hi')\n")
    (p / "pyproject.toml").write_text('[project]\nname="x"\nversion="1.0.0"\n[tool.pyxpo]\nname = "Demo"\n'
                                      'bundle_id = "com.acme.demo"\nmodules = ["video"]\n')
    out = web.build(p)
    html = (out / "index.html").read_text(encoding="utf-8")
    cfg = json.loads(html.split("window.PYXPO_CONFIG = ", 1)[1].split(";</script>", 1)[0])
    assert cfg["scripts"] == ["modules/Video.js"]
    assert (out / "modules" / "Video.js").read_text() == open(V.__path__[0] + "/web.js").read()


NODE_VIEW = r"""
const fs = require("fs");
let view, mod;
const made = [];
function el(tag) {
  const e = { tag, style: {}, attrs: {}, children: [], on: {}, calls: [],
    appendChild(c) { this.children.push(c); }, addEventListener(n, f) { this.on[n] = f; },
    removeAttribute(n) { delete this.attrs[n]; this.src = undefined; }, remove() { this.removed = true; },
    load() { this.calls.push("load"); }, pause() { this.calls.push("pause"); },
    play() { this.calls.push("play"); return Promise.resolve(); } };
  made.push(e);
  return e;
}
global.document = { createElement: el };
global.window = { pyxpoPage: { fileUrl: (p) => "/file?p=" + encodeURIComponent(p) } };
global.pyxpoPage = { defineView(t, f) { view = f; }, defineModule(n, f) { mod = f; } };
eval(fs.readFileSync(process.argv[2], "utf8"));
const events = [];
const host = el("div");
const v = view(host, (n, d) => events.push([n, d]));
const video = host.children[0];
v.update({ source: "/a b.mp4", playing: false, loop: true, muted: true, controls: true, resize_mode: "cover" });
video.duration = 3; video.videoWidth = 1080; video.videoHeight = 1920;
video.on.loadedmetadata();
v.update({ playing: true });
v.update({ source: "https://x.test/b.mp4" });
mod("seek", [1, 2.5], { view: () => v });
console.log(JSON.stringify({ src: video.src, loop: video.loop, muted: video.muted, controls: video.controls,
  fit: video.style.objectFit, calls: video.calls, events, t: video.currentTime }));
"""


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_web_js_drives_the_video_element(tmp_path):
    subprocess.run(["node", "--check", V.__path__[0] + "/web.js"], check=True)
    (tmp_path / "t.js").write_text(NODE_VIEW)
    out = subprocess.run(["node", str(tmp_path / "t.js"), V.__path__[0] + "/web.js"], check=True,
                         capture_output=True, text=True).stdout
    got = json.loads(out)
    assert got["src"] == "https://x.test/b.mp4" and got["loop"] and got["muted"] and got["controls"]
    assert got["fit"] == "cover" and got["t"] == 2.5
    assert got["calls"] == ["load", "pause", "play", "load", "play"]
    assert got["events"] == [["load", {"duration": 3, "width": 1080, "height": 1920}]]
