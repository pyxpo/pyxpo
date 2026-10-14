from __future__ import annotations

from pyxpo import Checkbox, Pressable, Switch, Text, View, component, use_state
from tests.test_core import mount


def first(r, type_):
    return r.find_all(type_)[0]


def test_pressable_press_state_and_events():
    log = []

    @component
    def App():
        return Pressable(Text("go"), on_press=lambda: log.append("press"), on_press_in=lambda: log.append("in"),
                         style={"opacity": 1.0})

    app, r = mount(App)
    v = first(r, "View")
    assert "on_press" in v.props and v.props["style"]["opacity"] == 1.0
    r.emit("press_in", v)
    assert first(r, "View").props["style"]["opacity"] == 0.6
    r.emit("press_out", v)
    r.emit("press", v)
    assert first(r, "View").props["style"]["opacity"] == 1.0
    assert log == ["in", "press"]


def test_pressable_disabled_has_no_handlers():
    @component
    def App():
        return Pressable(Text("x"), on_press=lambda: None, disabled=True, accessibility_label="Go")

    app, r = mount(App)
    p = first(r, "View").props
    assert "on_press" not in p and "on_press_in" not in p
    assert p["accessibility_state"] == {"disabled": True} and p["accessibility_label"] == "Go"


def test_pressable_style_and_child_callables():
    @component
    def App():
        return Pressable(render=lambda pressed: Text("down" if pressed else "up"),
                         style=lambda pressed: {"background_color": "#f00" if pressed else "#0f0"})

    app, r = mount(App)
    assert r.texts() == ["up"]
    r.emit("press_in", first(r, "View"))
    assert r.texts() == ["down"]
    assert first(r, "View").props["style"]["background_color"] == "#f00"


def test_switch_toggles():
    @component
    def App():
        on, set_on = use_state(False)
        return Switch(value=on, on_value_change=set_on, native=False)

    app, r = mount(App)
    sw = first(r, "View")
    assert sw.props["accessibility_role"] == "switch" and sw.props["accessibility_state"] == {"checked": False}
    r.press(sw)
    sw = first(r, "View")
    assert sw.props["accessibility_state"] == {"checked": True}
    assert sw.props["style"]["justify_content"] == "flex-end"


def test_checkbox_toggles_and_shows_check():
    @component
    def App():
        on, set_on = use_state(False)
        return View(Checkbox(value=on, on_value_change=set_on, native=False))

    app, r = mount(App)
    assert r.texts() == []
    r.press(r.find_all("View")[1])
    assert r.texts() == ["✓"]


def test_safe_area_and_keyboard():
    from pyxpo import KeyboardAvoidingView, SafeArea
    from pyxpo.env import Env  # noqa: F401

    def root():
        return SafeArea(Text("x"), avoid_keyboard=True, style={"padding": 4})

    app, r = mount(root)
    app.env.update({"insets": {"top": 30, "bottom": 20, "left": 0, "right": 0}})
    app.flush()
    st = r.find_all("View")[0].props["style"]
    assert st["padding_top"] == 34 and st["padding_bottom"] == 24 and "padding" not in st
    app.env.update({"keyboard": {"visible": True, "height": 300}})
    app.flush()
    assert r.find_all("View")[0].props["style"]["padding_bottom"] == 304

    app2, r2 = mount(lambda: KeyboardAvoidingView(Text("y"), offset=20))
    app2.env.update({"keyboard": {"visible": True, "height": 300}})
    app2.flush()
    assert r2.find_all("View")[0].props["style"]["padding_bottom"] == 280


def test_call_op_and_result():
    import asyncio
    from pyxpo import Clipboard, Keyboard
    app, r = mount(lambda: Text("a"))
    Keyboard.dismiss()
    assert r.calls[-1].module == "Keyboard" and r.calls[-1].method == "dismiss"
    loop = asyncio.new_event_loop()
    app.loop = loop

    async def go():
        t = asyncio.ensure_future(Clipboard.get_string())
        await asyncio.sleep(0)
        c = r.calls[-1]
        assert c.reply and c.method == "get_string"
        app._handle_event('{"event":"call_result","id":%d,"payload":{"value":"hi"}}' % c.id)
        return await t

    assert loop.run_until_complete(go()) == "hi"
    loop.close()


def test_native_controls_emit_single_host_with_colors_and_events():
    from pyxpo import ActivityIndicator, Slider
    from pyxpo.widgets import Radio
    from pyxpo.kit import ProgressBar
    seen = []

    @component
    def App():
        on, set_on = use_state(False)
        return View(Switch(value=on, on_value_change=lambda v: (seen.append(v), set_on(v)), track_color={"on": "#ff0000"}),
                    Checkbox(value=True), Slider(value=0.5), ProgressBar(value=0.3), ProgressBar(value=None),
                    ActivityIndicator(size="large"), Radio(selected=True, label="A"))

    app, r = mount(App)
    kinds = [n for n in ("NativeSwitch", "NativeCheckBox", "NativeSlider", "NativeProgress", "NativeSpinner",
                         "NativeRadio") if r.find_all(n)]
    assert len(kinds) == 6 and len(r.find_all("NativeProgress")) == 2
    sw = first(r, "NativeSwitch")
    assert sw.props["track_on"] == 0xFFFF0000 and sw.props["value"] is False
    r.emit("value_change", sw, {"value": True})
    assert seen == [True]
    assert first(r, "NativeSwitch").props["value"] is True
    bars = r.find_all("NativeProgress")
    assert bars[0].props["value"] == 0.3 and bars[1].props["indeterminate"] is True
