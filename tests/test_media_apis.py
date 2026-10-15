from __future__ import annotations

import asyncio
import os

import pytest

from pyxpo_sharing import Share, Sharing
from pyxpo_media_library import MediaLibrary
from pyxpo_image_picker import ImagePicker
from pyxpo.module_api import NotSupportedError
from pyxpo_image_manipulator import FlipType, ImageManipulator, ImageTooLargeError, SaveFormat
from pyxpo.apis import _bridge
from pyxpo_image_manipulator import centered_crop, fit_size, parse_ratio, search_under


class FakeApp:
    """Records native calls and answers from `handlers[(module, method)]`."""

    loop = None

    def __init__(self, handlers):
        self.handlers = handlers
        self.calls = []

    def call(self, module, method, *args, reply=False):
        self.calls.append((module, method, args))
        fut = asyncio.get_event_loop().create_future()
        out = self.handlers[(module, method)](*args)
        if isinstance(out, Exception):
            fut.set_exception(out)
        else:
            fut.set_result(out)
        return fut


def run(handlers, coro_fn):
    app = FakeApp(handlers)
    old = _bridge.get_app()
    _bridge.set_app(app)
    try:
        return asyncio.run(coro_fn()), app
    finally:
        _bridge.set_app(old)


def test_ratio_and_crop_math():
    assert parse_ratio("4:5") == 0.8
    with pytest.raises(ValueError):
        parse_ratio("square")
    assert centered_crop(4000, 3000, 1.0) == {"x": 500, "y": 0, "width": 3000, "height": 3000}
    assert centered_crop(3000, 4000, 16 / 9) == {"x": 0, "y": 1156, "width": 3000, "height": 1688}


def test_fit_size():
    assert fit_size(4000, 3000, {"width": 1080, "height": 1080}) == (1080, 1080)
    assert fit_size(4000, 3000, {"width": 1080, "height": 1080, "mode": "fit"}) == (1080, 810)
    assert fit_size(4000, 3000, {"width": 2000}) == (2000, 1500)
    with pytest.raises(ValueError):
        fit_size(10, 10, {})


def _model(tmp_path, base=4_000_000, floor=0.0):
    """Fake renderer: size ~ base * quality^2 * scale^2 (+floor); writes a real file so discards are observable."""
    files = []

    async def render(q, scale):
        p = tmp_path / ("r%d.jpg" % len(files))
        p.write_bytes(b"x")
        files.append(p)
        return {"uri": str(p), "fileSize": int(base * q * q * scale * scale + floor)}

    return render, files


def test_search_returns_first_try_when_it_fits(tmp_path):
    render, files = _model(tmp_path, base=1_000_000)
    out = asyncio.run(search_under(render, 2_000_000, 4000, 320))
    assert out["fileSize"] <= 2_000_000 and len(files) == 1


def test_search_picks_highest_quality_that_fits_and_cleans_up(tmp_path):
    render, files = _model(tmp_path)
    target = 1_000_000
    out = asyncio.run(search_under(render, target, 4000, 320))
    assert out["fileSize"] <= target and out["scale"] == 1.0
    assert 0.45 < out["quality"] < 0.52  # sqrt(1/4) = 0.5, found by bisection
    assert [p for p in files if p.exists()] == [__import__("pathlib").Path(out["uri"])]


def test_search_scales_down_when_quality_floor_is_not_enough(tmp_path):
    render, files = _model(tmp_path, base=40_000_000)
    out = asyncio.run(search_under(render, 500_000, 4000, 320))
    assert out["fileSize"] <= 500_000 and out["scale"] < 1.0
    assert sum(p.exists() for p in files) == 1


def test_search_gives_up_below_min_edge(tmp_path):
    render, files = _model(tmp_path, base=1_000, floor=10_000_000)
    with pytest.raises(ImageTooLargeError):
        asyncio.run(search_under(render, 1000, 4000, 320))
    assert not any(p.exists() for p in files)


def test_search_png_only_scales(tmp_path):
    files = []

    async def render(q, scale):
        assert q == 1.0
        p = tmp_path / ("p%d.png" % len(files))
        p.write_bytes(b"x")
        files.append(p)
        return {"uri": str(p), "fileSize": int(9_000_000 * scale * scale)}

    out = asyncio.run(search_under(render, 2_000_000, 4000, 320, lossy=False))
    assert out["fileSize"] <= 2_000_000 and sum(p.exists() for p in files) == 1


def _tools(log):
    def open_(path, max_edge):
        log.append(("open", path, max_edge))
        return {"h": 7, "width": 4000, "height": 3000, "sourceWidth": 8000, "sourceHeight": 6000}

    def render(h, spec):
        log.append(("render", h, spec))
        return {"uri": "/o.jpg", "fileSize": 10, "width": 1, "height": 1}

    def close(h):
        log.append(("close", h))

    return {("ImageManipulator", "open"): open_, ("ImageManipulator", "render"): render, ("ImageManipulator", "close"): close}


def test_manipulate_plans_ops_in_order_and_always_closes():
    log = []
    out, _ = run(_tools(log), lambda: ImageManipulator.manipulateAsync(
        "/a.heic", [{"rotate": 90}, {"resize": {"width": 1500}}, {"crop": {"originX": 0, "originY": 0, "width": 100, "height": 100}},
                    {"flip": FlipType.Horizontal}], {"compress": 0.8, "format": SaveFormat.PNG}))
    assert out["uri"] == "/o.jpg"
    assert log[0] == ("open", "/a.heic", 0)
    spec = log[1][2]
    # 4000x3000 rotated 90 -> 3000x4000; width 1500 keeps aspect -> 1500x2000
    assert spec["ops"] == [{"op": "rotate", "degrees": 90}, {"op": "resize", "width": 1500, "height": 2000},
                           {"op": "crop", "x": 0, "y": 0, "width": 100, "height": 100}, {"op": "flip", "axis": "horizontal"}]
    assert (spec["format"], spec["quality"]) == ("png", 0.8)
    assert log[-1] == ("close", 7)


def test_manipulate_validates_before_render():
    log = []
    for actions, exc in (([{"crop": {"originX": 3900, "originY": 0, "width": 200, "height": 10}}], ValueError),
                         ([{"rotate": 45}], NotSupportedError), ([{"spin": 1}], ValueError), ([{"resize": {}}], ValueError)):
        with pytest.raises(exc):
            run(_tools(log), lambda: ImageManipulator.manipulateAsync("/a.jpg", actions))
    assert all(c[0] != "render" for c in log) and log.count(("close", 7)) == 4
    with pytest.raises(ValueError):
        run(_tools(log), lambda: ImageManipulator.manipulateAsync("/a.jpg", [], {"compress": 2}))


def test_manipulate_not_supported_formats_raise_before_native_call(monkeypatch):
    from pyxpo.apis import _env
    log = []
    monkeypatch.setattr(_env, "current", _env.Env({"os": "ios", "modules": ["ImageManipulator"]}))
    with pytest.raises(NotSupportedError):
        run(_tools(log), lambda: ImageManipulator.manipulateAsync("/a.jpg", [], {"format": SaveFormat.WEBP}))
    monkeypatch.setattr(_env, "current", _env.Env({"os": "android", "modules": ["ImageManipulator"]}))
    with pytest.raises(NotSupportedError):
        run(_tools(log), lambda: ImageManipulator.manipulateAsync("/a.jpg", [], {"format": SaveFormat.HEIC}))
    assert log == []


def test_manipulate_base64(tmp_path):
    f = tmp_path / "o.jpg"
    f.write_bytes(b"abc")
    h = _tools([])
    h[("ImageManipulator", "render")] = lambda hh, spec: {"uri": str(f), "fileSize": 3}
    out, _ = run(h, lambda: ImageManipulator.manipulateAsync("/a.jpg", [], {"base64": True}))
    assert out["base64"] == "YWJj"


def test_manipulate_closes_handle_on_native_error():
    log = []
    h = _tools(log)
    h[("ImageManipulator", "render")] = lambda hh, spec: RuntimeError("boom")
    with pytest.raises(RuntimeError, match="boom"):
        run(h, lambda: ImageManipulator.manipulateAsync("/a.jpg"))
    assert ("close", 7) in log


def test_compress_to_size_uses_search_and_closes(tmp_path):
    log = []
    h = _tools(log)
    n = []

    def render(hh, spec):
        p = tmp_path / ("c%d.jpg" % len(n))
        p.write_bytes(b"x")
        n.append(p)
        return {"uri": str(p), "fileSize": int(4_000_000 * spec["quality"] ** 2)}

    h[("ImageManipulator", "render")] = render
    out, _ = run(h, lambda: ImageManipulator.compressToSizeAsync("/a.jpg", 1_000_000))
    assert out["fileSize"] <= 1_000_000
    assert log[0] == ("open", "/a.jpg", 4096) and log[-1] == ("close", 7)
    with pytest.raises(ValueError):
        run(h, lambda: ImageManipulator.compressToSizeAsync("/a.jpg", 0))


def test_picker_media_types_and_limit_normalization():
    h = {("ImagePicker", "pick"): lambda m, l, k: {"assets": [{"uri": "/v.mov", "type": "video"}]}}
    cases = [
        (dict(mediaTypes=["images", "videos"], allowsMultipleSelection=True), (True, 0, "all")),
        (dict(mediaTypes="videos"), (False, 0, "videos")),
        (dict(allowsMultipleSelection=True, selectionLimit=1), (False, 0, "images")),  # a limit of 1 is a single pick
        (dict(selectionLimit=5), (False, 0, "images")),  # limit means nothing without multiple selection
    ]
    for kw, want in cases:
        _, app = run(h, lambda: ImagePicker.launchImageLibraryAsync(**kw))
        assert app.calls[0][2] == want
    for kw, exc in ((dict(mediaTypes="audio"), ValueError), (dict(mediaTypes=[]), ValueError),
                    (dict(mediaTypes="livePhotos"), NotSupportedError), (dict(selectionLimit=-1), ValueError)):
        with pytest.raises(exc):
            run(h, lambda: ImagePicker.launchImageLibraryAsync(**kw))


def test_share_links_go_into_message_and_sharing_shape():
    h = {("Share", "share"): lambda urls, msg, mime, title: {"action": "sharedAction"}}
    _, app = run(h, lambda: Share.share({"urls": ["/a.jpg", "https://x.dev/p"], "message": "hi"}, {"dialogTitle": "Send"}))
    assert app.calls[0][2] == (["/a.jpg"], "hi\nhttps://x.dev/p", "", "Send")
    _, app = run(h, lambda: Share.share({"url": "https://x.dev"}))
    assert app.calls[0][2] == ([], "https://x.dev", "", "")
    _, app = run(h, lambda: Sharing.shareAsync("/a.pdf", {"mimeType": "application/pdf", "dialogTitle": "T"}))
    assert app.calls[0][2] == (["/a.pdf"], "", "application/pdf", "T")
    with pytest.raises(ValueError):
        run(h, lambda: Sharing.shareAsync("https://x.dev"))


def test_share_rejects_second_sheet_and_resets_after_error():
    async def both():
        first = asyncio.ensure_future(Share.share({"url": "/a"}))
        await asyncio.sleep(0)
        with pytest.raises(RuntimeError, match="already open"):
            await Share.share({"url": "/b"})
        gate.set_result({"action": "dismissedAction"})
        return await first

    gate = None

    class SlowApp(FakeApp):
        def call(self, module, method, *args, reply=False):
            return gate

    async def go():
        nonlocal gate
        gate = asyncio.get_event_loop().create_future()
        return await both()

    old = _bridge.get_app()
    _bridge.set_app(SlowApp({}))
    try:
        assert asyncio.run(go()) == {"action": "dismissedAction"}
    finally:
        _bridge.set_app(old)
    out, _ = run({("Share", "share"): lambda *a: RuntimeError("boom")}, lambda: _boom())
    assert out == "boom"
    out, _ = run({("Share", "share"): lambda *a: {"action": "sharedAction"}}, lambda: Share.share({"url": "/a"}))
    assert out["action"] == "sharedAction"


async def _boom():
    try:
        await Share.share({"url": "/a"})
    except RuntimeError as e:
        return str(e)


def test_picker_share_and_library_shapes():
    out, app = run({("ImagePicker", "pick"): lambda multi, limit, kinds: {"assets": [{"uri": "/x.jpg"}]}},
                   lambda: ImagePicker.launch_image_library_async(allowsMultipleSelection=True, selectionLimit=3))
    assert out == {"canceled": False, "assets": [{"uri": "/x.jpg"}]}
    assert app.calls[0][2] == (True, 3, "images")
    out, _ = run({("ImagePicker", "pick"): lambda m, l, k: {"assets": []}}, lambda: ImagePicker.launchImageLibraryAsync())
    assert out == {"canceled": True, "assets": []}

    out, app = run({("Share", "share"): lambda urls, msg, mime, title: {"action": "sharedAction"}},
                   lambda: Share.share({"urls": ["/a", "/b"]}))
    assert out == {"action": "sharedAction"} and app.calls[0][2] == (["/a", "/b"], "", "", "")
    with pytest.raises(ValueError):
        run({}, lambda: Share.share({}))

    _, app = run({("MediaLibrary", "save"): lambda p: None}, lambda: MediaLibrary.saveToLibraryAsync("/a.jpg"))
    assert app.calls[0][:2] == ("MediaLibrary", "save")


def test_library_permissions_expo_shape_and_default_is_read_write():
    h = {("MediaLibrary", "request_permission"): lambda w: {"status": "granted", "canAskAgain": True, "accessPrivileges": "limited"},
         ("MediaLibrary", "get_permission"): lambda w: {"status": "undetermined", "canAskAgain": True}}
    out, app = run(h, lambda: MediaLibrary.requestPermissionsAsync())
    assert out == {"status": "granted", "granted": True, "canAskAgain": True, "expires": "never", "accessPrivileges": "limited"}
    assert app.calls[0][2] == (False,)
    out, app = run(h, lambda: MediaLibrary.get_permissions_async(writeOnly=True))
    assert out == {"status": "undetermined", "granted": False, "canAskAgain": True, "expires": "never", "accessPrivileges": "none"}
    assert app.calls[0][:3] == ("MediaLibrary", "get_permission", (True,))
    out, _ = run({("MediaLibrary", "get_permission"): lambda w: {"status": "denied", "canAskAgain": False}},
                 lambda: MediaLibrary.getPermissionsAsync())
    assert out["granted"] is False and out["canAskAgain"] is False and out["accessPrivileges"] == "none"
    with pytest.raises(ValueError):  # a bad native status is not passed through
        run({("MediaLibrary", "get_permission"): lambda w: {"status": "maybe"}}, lambda: MediaLibrary.getPermissionsAsync())


def test_library_create_asset_validates_before_native_call():
    asset = {"id": "1", "uri": "content://media/1", "mediaType": "video", "width": 1920, "height": 1080,
             "duration": 2.5, "filename": "clip.mp4"}
    out, app = run({("MediaLibrary", "create"): lambda p: asset}, lambda: MediaLibrary.createAssetAsync("file:///c/clip.mp4"))
    assert out == asset and app.calls[0][2] == ("file:///c/clip.mp4",)
    for bad in ("", None, "https://x.dev/a.jpg", "content://media/1"):
        with pytest.raises(ValueError):
            run({}, lambda: MediaLibrary.createAssetAsync(bad))
        with pytest.raises(ValueError):
            run({}, lambda: MediaLibrary.saveToLibraryAsync(bad))


def test_camera_launch_args_and_shape(monkeypatch):
    from pyxpo.apis import _env
    h = {("ImagePicker", "camera"): lambda kinds, secs: {"assets": [{"uri": "/c.jpg", "type": "image"}]}}
    out, app = run(h, lambda: ImagePicker.launchCameraAsync())
    assert out == {"canceled": False, "assets": [{"uri": "/c.jpg", "type": "image"}]}
    assert app.calls[0][:3] == ("ImagePicker", "camera", ("images", 0.0))
    _, app = run(h, lambda: ImagePicker.launch_camera_async(mediaTypes="videos", videoMaxDuration=15))
    assert app.calls[0][2] == ("videos", 15.0)
    out, _ = run({("ImagePicker", "camera"): lambda k, s: {"assets": []}}, lambda: ImagePicker.launchCameraAsync())
    assert out == {"canceled": True, "assets": []}
    for kw, exc in ((dict(mediaTypes="audio"), ValueError), (dict(videoMaxDuration=-1), ValueError),
                    (dict(videoMaxDuration="10"), ValueError), (dict(videoMaxDuration=True), ValueError)):
        with pytest.raises(exc):
            run({}, lambda: ImagePicker.launchCameraAsync(**kw))
    # photo and video in one capture: iOS only, refused on Android before the native call
    monkeypatch.setattr(_env, "current", _env.Env({"os": "android", "modules": ["ImagePicker"]}))
    with pytest.raises(NotSupportedError):
        run({}, lambda: ImagePicker.launchCameraAsync(mediaTypes=["images", "videos"]))
    monkeypatch.setattr(_env, "current", _env.Env({"os": "ios", "modules": ["ImagePicker"]}))
    _, app = run(h, lambda: ImagePicker.launchCameraAsync(mediaTypes=["images", "videos"]))
    assert app.calls[0][2] == ("all", 0.0)


def test_camera_permissions_expo_shape():
    h = {("ImagePicker", "camera_permission"): lambda ask: {"status": "granted" if ask else "undetermined", "canAskAgain": True}}
    out, app = run(h, lambda: ImagePicker.getCameraPermissionsAsync())
    assert out == {"status": "undetermined", "granted": False, "canAskAgain": True, "expires": "never"}
    assert app.calls[0][2] == (False,)
    out, app = run(h, lambda: ImagePicker.request_camera_permissions_async())
    assert out == {"status": "granted", "granted": True, "canAskAgain": True, "expires": "never"}
    assert app.calls[0][2] == (True,)
