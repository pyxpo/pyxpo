from __future__ import annotations

from pyxpo import Modal, Slider, Text, View, component, use_pan_responder, use_state

from .test_core import mount


def test_slider_touch_and_layout():
    seen = []

    @component
    def App():
        v, set_v = use_state(0.0)

        def ch(x):
            seen.append(x)
            set_v(x)
        return Slider(value=v, minimum=0, maximum=100, on_value_change=ch)

    app, r = mount(App)
    root = r.find_all("View")[0]
    r.emit("layout", root, {"value": {"x": 0, "y": 0, "width": 328, "height": 28}})
    app.flush() if hasattr(app, "flush") else None
    r.emit("touch_start", root, {"value": {"x": 164, "y": 10}})
    assert seen and abs(seen[-1] - 50) < 1e-6
    r.emit("touch_move", root, {"value": {"x": 1000, "y": 10}})
    assert seen[-1] == 100


def test_pan_responder_deltas():
    got = []

    @component
    def App():
        pan = use_pan_responder(on_move=lambda g: got.append((g.dx, g.dy)))
        return View(Text("x"), **pan)

    app, r = mount(App)
    v = r.find_all("View")[0]
    r.emit("touch_start", v, {"value": {"x": 10, "y": 20}})
    r.emit("touch_move", v, {"value": {"x": 15, "y": 17}})
    assert got[-1] == (5, -3)


def test_modal_visibility_and_root_type():
    @component
    def App():
        vis, set_vis = use_state(False)
        return View(Modal(Text("hi"), visible=vis, on_request_close=lambda: set_vis(False)))

    app, r = mount(App)
    assert not r.find_all("Modal")


def test_modal_visible_renders_native_modal():
    @component
    def App():
        return View(Modal(Text("hi"), visible=True))

    app, r = mount(App)
    assert len(r.find_all("Modal")) == 1
    assert r.find_text("hi")
