from __future__ import annotations

from pyxpo import Modal, PanResponder, Text, View, component, use_state

from .test_core import mount


def test_pan_responder_deltas():
    got = []
    pan = PanResponder.create({"onPanResponderMove": lambda e, g: got.append((g.dx, g.dy))})

    @component
    def App():
        return View(Text("x"), **pan.panHandlers)

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


def test_pan_responder_keeps_fling_velocity_on_release():
    got = {}
    pan = PanResponder.create({"onPanResponderRelease": lambda e, g: got.update(vx=g.vx, dx=g.dx)})

    @component
    def App():
        return View(Text("x"), **pan.panHandlers)

    app, r = mount(App)
    v = r.find_all("View")[0]
    r.emit("touch_start", v, {"value": {"x": 10, "y": 20}})
    r.emit("touch_move", v, {"value": {"x": 60, "y": 20}})
    r.emit("touch_end", v, {"value": {"x": 60, "y": 20}})  # release at the last move point
    assert got["dx"] == 50 and got["vx"] > 0


def _modal_app(box, animation_type):
    @component
    def App():
        vis, set_vis = use_state(True)
        box["set"] = set_vis
        return View(Modal(Text("hi"), visible=vis, animation_type=animation_type))
    return App


def test_modal_interrupted_fade_out_does_not_unmount():
    box = {}
    app, r = mount(_modal_app(box, "fade"))
    box["set"](False)
    r.advance(100)
    box["set"](True)   # interrupts the fade-out
    r.advance(500)
    assert r.find_all("Modal")
    box["set"](False)
    # A new fade-out must play: the layer stays until it finishes.
    assert r.find_all("Modal")
    r.advance(500)
    assert not r.find_all("Modal")


def test_modal_slide_does_not_create_nodes_per_render(monkeypatch):
    box = {}

    @component
    def App():
        n, set_n = use_state(0)
        box["set"] = set_n
        return View(Modal(Text("hi %d" % n), visible=True, animation_type="slide"))

    app, r = mount(App)
    before = len(r.driver.nodes)
    for i in range(1, 6):
        box["set"](i)
    assert len(r.driver.nodes) == before
