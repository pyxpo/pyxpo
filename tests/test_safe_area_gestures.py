from __future__ import annotations

from pyxpo import LocalChannel, Text, View, component, create_app, create_context, use_context
from pyxpo.gesture_handler import Gesture, GestureDetector
from pyxpo.renderers.mock import MockRenderer
from pyxpo.safe_area import SafeAreaInsetsContext, SafeAreaProvider, useSafeAreaFrame, useSafeAreaInsets


def mount(root):
    ch = LocalChannel()
    r = MockRenderer(ch)
    create_app(root, ch)
    return r


@component
def Leaf():
    i, f = useSafeAreaInsets(), useSafeAreaFrame()
    return Text("t%d w%d" % (i["top"], f["width"]))


def test_safe_area_provider_overrides_device_values():
    r = mount(lambda: View(Leaf(), SafeAreaProvider(Leaf(), initial_metrics={"insets": {"top": 44}, "frame": {"width": 100}})))
    assert r.texts()[1] == "t44 w100" and r.texts()[0] != "t44 w100"


def test_context_consumer_and_nested_providers():
    Theme = create_context("light")
    r = mount(lambda: View(Theme.Consumer(lambda v: Text("a:" + v)),
                           Theme.Provider(Theme.Provider(Theme.Consumer(lambda v: Text("b:" + v)), value="x"), value="dark")))
    assert r.texts() == ["a:light", "b:x"]


def test_drawer_items_respect_top_inset():
    from pyxpo.router.layouts.drawer import DrawerItems
    r = mount(lambda: SafeAreaProvider(DrawerItems(items=[{"key": "a", "label": "A"}], title="Menu"),
                                       initial_metrics={"insets": {"top": 47, "bottom": 34}}))
    t = r.find_text("Menu")
    assert t.props["style"]["padding_top"] == 16 + 47


def _touch(r, node, kind, x, y):
    r.emit(kind, node, {"value": {"x": x, "y": y, "page_x": x, "page_y": y}})


def test_pan_and_tap_gestures():
    log = []
    pan = (Gesture.Pan().onBegin(lambda e: log.append("begin")).onStart(lambda e: log.append("start"))
           .onUpdate(lambda e: log.append(round(e["translationX"]))).onEnd(lambda e, ok: log.append(("end", ok))))
    tap = Gesture.Tap().onEnd(lambda e, ok: log.append(("tap", ok)))
    r = mount(lambda: GestureDetector(View(Text("x")), gesture=Gesture.Exclusive(pan, tap)))
    v = [n for n in r.find_all("View") if n.props.get("on_touch_start")][0]
    _touch(r, v, "touch_start", 0, 0); _touch(r, v, "touch_move", 30, 0); _touch(r, v, "touch_end", 30, 0)
    assert log[:3] == ["begin", "start", 30] and ("end", True) in log and ("tap", True) not in log
    del log[:]
    _touch(r, v, "touch_start", 5, 5); _touch(r, v, "touch_end", 5, 5)
    assert ("tap", True) in log
