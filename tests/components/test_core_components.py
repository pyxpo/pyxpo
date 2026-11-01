from __future__ import annotations

from pyxpo import (ActivityIndicator, Button, Pressable, SafeAreaView, Slider, Switch, Text, TouchableOpacity, View,
                   component, use_state)
from tests.test_core import mount


def first(r, type_):
    return r.find_all(type_)[0]


def test_pressable_events_and_state():
    log = []

    @component
    def App():
        return Pressable(Text("go"), on_press=lambda: log.append("press"), on_press_in=lambda: log.append("in"),
                         on_press_out=lambda: log.append("out"),
                         style=lambda s: {"background_color": "#f00" if s.pressed else "#0f0"})

    app, r = mount(App)
    v = first(r, "View")
    assert v.props["style"]["background_color"] == 0xFF00FF00
    r.emit("press_in", v)
    assert first(r, "View").props["style"]["background_color"] == 0xFFFF0000
    r.emit("press_out", v)
    r.emit("press", v)
    assert log == ["in", "out", "press"]


def test_pressable_disabled_has_no_handlers():
    app, r = mount(lambda: Pressable(Text("x"), on_press=lambda: None, disabled=True, accessibility_label="Go"))
    p = first(r, "View").props
    assert "on_press" not in p and "on_press_in" not in p
    assert p["accessibility_state"] == {"disabled": True} and p["accessibility_label"] == "Go"


def test_pressable_function_child_and_camel_props():
    got = []
    app, r = mount(lambda: Pressable(lambda s: Text("down" if s.pressed else "up"), onPress=lambda: got.append(1)))
    assert r.texts() == ["up"]
    r.emit("press_in", first(r, "View"))
    assert r.texts() == ["down"]
    r.press(first(r, "View"))
    assert got == [1]


def test_touchable_opacity_dims_while_pressed():
    app, r = mount(lambda: TouchableOpacity(Text("t"), onPress=lambda: None, activeOpacity=0.5))
    v = first(r, "View")
    r.emit("press_in", v)
    assert first(r, "View").props["style"]["opacity"] == 0.5
    r.emit("press_out", v)
    assert first(r, "View").props["style"].get("opacity", 1) == 1


def test_button_title_press_and_disabled():
    got = []
    app, r = mount(lambda: Button(title="Save", onPress=lambda: got.append(1)))
    r.press(r.find_text("Save"))
    assert got == [1]
    app2, r2 = mount(lambda: Button(title="Save", onPress=lambda: got.append(2), disabled=True))
    r2.press(r2.find_text("Save"))
    assert got == [1]


def test_switch_single_native_host_and_events():
    seen = []

    @component
    def App():
        on, set_on = use_state(False)
        return Switch(value=on, onValueChange=lambda v: (seen.append(v), set_on(v)), trackColor={True: "#ff0000"})

    app, r = mount(App)
    sw = first(r, "NativeSwitch")
    assert sw.props["track_on"] == 0xFFFF0000 and sw.props["value"] is False
    r.emit("value_change", sw, {"value": True})
    assert seen == [True] and first(r, "NativeSwitch").props["value"] is True


def test_slider_and_activity_indicator_hosts():
    app, r = mount(lambda: View(Slider(value=5, minimumValue=0, maximumValue=10), ActivityIndicator(size="large")))
    s = first(r, "NativeSlider")
    assert s.props["minimum"] == 0.0 and s.props["maximum"] == 10.0
    assert len(r.find_all("NativeSpinner")) == 1


def test_safe_area_view_insets_and_style_padding():
    app, r = mount(lambda: SafeAreaView(Text("x"), style={"padding": 4}))
    app.env.update({"insets": {"top": 30, "bottom": 20, "left": 0, "right": 0}})
    app.flush()
    st = first(r, "View").props["style"]
    assert st["padding_top"] == 34 and st["padding_bottom"] == 24 and st["padding_left"] == 4 and "padding" not in st


def test_image_relative_path_resolves_from_project_root(monkeypatch, tmp_path):
    import types
    import sys
    from pyxpo import Image
    app_pkg = types.ModuleType("app")
    app_pkg.__path__ = [str(tmp_path / "app")]
    monkeypatch.setitem(sys.modules, "app", app_pkg)
    assert Image(source="assets/p.png").props["source"]["uri"] == str(tmp_path / "assets" / "p.png")
