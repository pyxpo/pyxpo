from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pyxpo import LocalChannel, component, use_state
from pyxpo.apis import _bridge, _env
from pyxpo.app import create_app
from pyxpo.module_api import dispatch
from pyxpo.renderers.mock import MockRenderer
from pyxpo import ImageViewer
from pyxpo.components.image_viewer import _options, _uris

RUNTIME = Path(__file__).resolve().parents[1] / "src/pyxpo/templates"
URLS = ["https://x.test/a.jpg", "https://x.test/b.jpg", "https://x.test/c.jpg"]


class FakeBridge:
    """Records native calls and keeps the `open` reply future to finish later."""

    def __init__(self):
        self.calls = []
        self.open = None

    def call(self, module, method, *args, reply=False):
        self.calls.append((module, method, args))
        if reply:
            self.open = asyncio.get_running_loop().create_future()
            return self.open
        return None


def mount(os_name="ios", modules=(), **props):
    box = {"closed": 0, "moves": []}

    @component
    def Root():
        visible, set_visible = use_state(False)
        box["show"] = set_visible

        def close():
            box["closed"] += 1
            set_visible(False)

        kw = dict(images=[{"uri": u} for u in URLS], image_index=1, visible=visible, on_request_close=close,
                  on_image_index_change=box["moves"].append)
        kw.update(props)
        return ImageViewer(**kw)

    ch = LocalChannel()
    r = MockRenderer(ch)
    box["app"] = create_app(Root, ch)
    _env.current = _env.Env({"os": os_name, "modules": list(modules)})  # after mount: the app resets the env
    return r, box


def fake(box):
    fb = FakeBridge()
    box["app"].call = fb.call  # the app keeps rendering; only native calls go to the fake
    return fb


@pytest.fixture(autouse=True)
def restore():
    old = (_bridge._app, _env.current)
    yield
    _bridge._app, _env.current = old


async def tick():
    for _ in range(3):
        await asyncio.sleep(0)


def test_uris_accept_strings_and_source_dicts():
    assert _uris(["/a.jpg", {"uri": "https://x/b.png"}]) == ["/a.jpg", "https://x/b.png"]
    for bad in ("/a.jpg", {"uri": "/a.jpg"}, [{"url": "/a.jpg"}], [""], [None]):
        with pytest.raises(ValueError):
            _uris(bad)


def test_options_clamp_index_and_check_max_zoom():
    o = _options(9, 3, "#111", False, True, 3, False, "")
    assert o == {"index": 2, "background": "#111", "swipeToClose": False, "doubleTapZoom": True, "maxZoom": 3.0,
                 "showCount": False, "closeLabel": "Close"}
    assert _options(-4, 3, "#000", True, True, 4, True, "X")["index"] == 0
    for bad in (0.5, True, "4"):
        with pytest.raises(ValueError):
            _options(0, 3, "#000", True, True, bad, True, "X")


def test_native_open_sends_uris_and_options_then_close_reports():
    async def go():
        r, box = mount()
        fb = fake(box)
        assert fb.calls == []
        box["show"](True)
        await tick()
        (module, method, args), = fb.calls
        assert (module, method) == ("ImageViewer", "open")
        assert args[0] == URLS and args[1]["index"] == 1 and args[1]["maxZoom"] == 4.0
        dispatch({"name": "ImageViewer.index", "data": {"index": 2}})
        assert box["moves"] == [2]
        fb.open.set_result({"index": 2})  # user swiped down
        await tick()
        assert box["closed"] == 1
        assert [c[1] for c in fb.calls] == ["open"]  # closed natively: no extra close call
        dispatch({"name": "ImageViewer.index", "data": {"index": 0}})
        assert box["moves"] == [2]  # unsubscribed
        assert r.find_all("Modal") == []

    asyncio.run(go())


def test_app_hiding_the_viewer_closes_it_natively_once():
    async def go():
        _, box = mount(os_name="android")
        fb = fake(box)
        box["show"](True)
        await tick()
        box["show"](False)
        await tick()
        assert [c[1] for c in fb.calls] == ["open", "close"]
        fb.open.set_result({"index": 1})
        await tick()
        assert box["closed"] == 0  # the app closed it itself: no on_request_close

    asyncio.run(go())


def test_web_shows_a_modal_with_count_and_paging():
    r, box = mount(os_name="web")
    assert r.find_text("2 / 3") is None
    box["show"](True)
    assert r.find_text("2 / 3") is not None
    nodes = {n.props.get("test_id"): n for n in r.root.walk() if n.props.get("test_id")}
    r.press(nodes["image-viewer-next"])
    assert r.find_text("3 / 3") is not None and box["moves"] == [2]
    nodes = {n.props.get("test_id"): n for n in r.root.walk() if n.props.get("test_id")}
    assert "image-viewer-next" not in nodes
    r.press(nodes["image-viewer-close"])
    assert box["closed"] == 1 and r.find_text("3 / 3") is None


def test_empty_images_render_nothing():
    r, box = mount(os_name="web", images=[])
    box["show"](True)
    assert r.find_all("Modal") == []


def test_native_sources_are_built_into_the_runtime():
    swift = (RUNTIME / "ios/gen/runtime/ImageViewer.swift").read_text()
    assert 'moduleName = "ImageViewer"' in swift and '"ImageViewer.index"' in swift
    assert "[ImageViewerModule.self] + pxModules" in (RUNTIME / "ios/gen/runtime/PxModule.swift").read_text()
    kt = RUNTIME / "android/gen/runtime/java/dev/pyxpo/runtime"
    viewer = (kt / "ImageViewer.kt").read_text()
    assert 'name = "ImageViewer"' in viewer and "listOf<PxModule>(ImageViewerModule()) + pxModules" in viewer
    assert "import androidx" not in viewer  # the runtime has no androidx dependency
    assert "allModules.associateBy" in (kt / "PxModuleHost.kt").read_text()
    assert "allModules.map" in (kt / "OpApplier.kt").read_text()
    for f in ("ZoomImageView.kt", "BitmapLoader.kt"):
        assert (kt / f).read_text().startswith("package dev.pyxpo.runtime")
