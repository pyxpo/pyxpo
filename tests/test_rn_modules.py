from __future__ import annotations

import asyncio

from pyxpo import Alert, BackHandler, Dimensions, Keyboard, Platform, Pressable, Text, component
from pyxpo import env, modules

from .test_core import mount


def test_platform_OS_and_os():
    assert Platform.OS == Platform.os()
    assert Platform.select({Platform.OS: "me", "default": "d"}) == "me"
    assert Platform.select({"nope": 1, "default": "d"}) == "d"


def test_dimensions_listener_remove():
    got = []
    sub = Dimensions.addEventListener("change", got.append)
    d = env.current._data
    old = d["window"]
    try:
        d["window"] = {**old, "width": old["width"] + 10}
        env.current._notify() if hasattr(env.current, "_notify") else [f() for f in list(env.current._listeners)]
        assert len(got) == 1 and got[0]["window"]["width"] == old["width"] + 10
        sub.remove()
        d["window"] = {**old, "width": old["width"] + 20}
        [f() for f in list(env.current._listeners)]
        assert len(got) == 1
    finally:
        d["window"] = old


def test_alert_alias_from_pyxpo():
    assert Alert.alert is modules.Alert.alert
    assert callable(Alert)


def test_alert_buttons_callbacks():
    calls = []

    class FakeApp:
        loop = None

        def call(self, mod, meth, *a, reply=False):
            fut = asyncio.get_event_loop().create_future()
            fut.set_result(1)
            return fut

    old = modules._app
    modules._app = FakeApp()
    try:
        co = Alert.alert("t", "m", [{"text": "No"}, {"text": "Yes", "onPress": lambda: calls.append("yes")}])
        assert asyncio.run(co) == 1 and calls == ["yes"]
    finally:
        modules._app = old


def test_backhandler_order_and_remove():
    order = []
    a = BackHandler.addEventListener("hardwareBackPress", lambda: order.append("a") or True)
    b = BackHandler.addEventListener("hardwareBackPress", lambda: order.append("b") or False)
    try:
        for fn in reversed(list(modules.Back._handlers)):
            if fn():
                break
        assert order == ["b", "a"]
        b.remove()
        assert len(modules.Back._handlers) >= 1
    finally:
        a.remove()


def test_keyboard_listener_edges():
    seen = []
    sub = Keyboard.addListener("keyboardDidShow", seen.append)
    kb = env.current._data["keyboard"]
    old = dict(kb)
    try:
        kb["visible"], kb["height"] = True, 300.0
        [f() for f in list(env.current._listeners)]
        [f() for f in list(env.current._listeners)]
        assert seen == [{"height": 300.0}]
    finally:
        sub.remove()
        kb.update(old)


def test_pressable_style_fn_gets_pressstate():
    got = []

    @component
    def App():
        return Pressable(Text("x"), style=lambda s: got.append((bool(s), s.pressed, s["pressed"])) or {}, test_id="btn")

    app, r = mount(App)
    assert got[0] == (False, False, False)
    v = r.find_all("View")[0]
    assert v.props["test_id"] == "btn"
