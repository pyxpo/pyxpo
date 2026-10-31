from __future__ import annotations

import asyncio

from pyxpo import Alert, BackHandler, Dimensions, Keyboard, Platform, Pressable, Text, component
from pyxpo.apis import _bridge, _env
from pyxpo.apis.back_handler import _Back

from .test_core import mount


def test_platform_OS_and_select():
    assert isinstance(Platform.OS, str)
    assert Platform.select({Platform.OS: "me", "default": "d"}) == "me"
    assert Platform.select({"nope": 1, "default": "d"}) == "d"


def test_dimensions_listener_remove():
    got = []
    sub = Dimensions.addEventListener("change", got.append)
    env = _env.current
    old = dict(env._data["window"])
    try:
        env.update({"window": {"width": old["width"] + 10}})
        assert len(got) == 1 and got[0]["window"]["width"] == old["width"] + 10
        sub.remove()
        env.update({"window": {"width": old["width"] + 20}})
        assert len(got) == 1
    finally:
        env.update({"window": old})


def test_alert_buttons_callbacks():
    calls = []

    class FakeApp:
        loop = None

        def call(self, mod, meth, *a, reply=False):
            fut = asyncio.get_event_loop().create_future()
            fut.set_result(1)
            return fut

    old = _bridge.get_app()
    _bridge.set_app(FakeApp())
    try:
        co = Alert.alert("t", "m", [{"text": "No"}, {"text": "Yes", "onPress": lambda: calls.append("yes")}])
        assert asyncio.run(co) == 1 and calls == ["yes"]
    finally:
        _bridge.set_app(old)


def test_backhandler_order_and_remove():
    order = []
    a = BackHandler.addEventListener("hardwareBackPress", lambda: order.append("a") or True)
    b = BackHandler.addEventListener("hardwareBackPress", lambda: order.append("b") or False)
    try:
        for fn in reversed(list(_Back.handlers)):
            if fn():
                break
        assert order == ["b", "a"]
        b.remove()
        assert len(_Back.handlers) == 1
    finally:
        a.remove()
    assert _Back.handlers == []


def test_keyboard_listener_edges():
    seen = []
    sub = Keyboard.addListener("keyboardDidShow", seen.append)
    env = _env.current
    try:
        env.update({"keyboard": {"visible": True, "height": 300.0}})
        env.update({"keyboard": {"visible": True, "height": 300.0}})
        assert len(seen) == 1 and seen[0]["endCoordinates"]["height"] == 300.0
    finally:
        sub.remove()
        env.update({"keyboard": {"visible": False, "height": 0.0}})


def test_keyboard_dismiss_emits_call_op():
    app, r = mount(lambda: Text("a"))
    Keyboard.dismiss()
    assert r.calls[-1].module == "Keyboard" and r.calls[-1].method == "dismiss"


def test_pressable_style_fn_gets_press_state():
    got = []

    @component
    def App():
        return Pressable(Text("x"), style=lambda s: got.append((bool(s), s.pressed, s["pressed"])) or {}, testID="btn")

    app, r = mount(App)
    assert got[0] == (False, False, False)
    assert r.find_all("View")[0].props["test_id"] == "btn"


def test_i18n_manager_direction():
    from pyxpo import I18nManager
    from pyxpo.apis import i18n_manager

    sent, seen = [], []

    class FakeApp:
        def call(self, mod, meth, *a, reply=False):
            sent.append((mod, meth) + a)

    old_app, old_state = _bridge.get_app(), dict(i18n_manager._state)
    env = _env.current
    _bridge.set_app(FakeApp())
    sub = I18nManager.addListener(seen.append)
    try:
        env.update({"rtl": True})
        i18n_manager._sync()
        assert I18nManager.isRTL is False and sent == []  # LTR until the app opts in
        I18nManager.allowRTL(True)
        assert I18nManager.isRTL is True and sent == [("I18nManager", "set_rtl", True)] and seen == [True]
        I18nManager.allowRTL(True)
        assert len(sent) == 1  # no repeat when nothing changed
        env.update({"rtl": False})
        I18nManager.allowRTL(True)
        assert I18nManager.isRTL is False and sent[-1] == ("I18nManager", "set_rtl", False)
        I18nManager.forceRTL(True)
        assert I18nManager.isRTL is True and seen == [True, False, True]
        sub.remove()
        I18nManager.forceRTL(False)
        assert seen == [True, False, True]
    finally:
        env.update({"rtl": False})
        _bridge.set_app(old_app)
        i18n_manager._state.update(old_state)
        i18n_manager._sync()
