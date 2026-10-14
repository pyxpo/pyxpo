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
        return Switch(value=on, on_value_change=set_on)

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
        return View(Checkbox(value=on, on_value_change=set_on))

    app, r = mount(App)
    assert r.texts() == []
    r.press(r.find_all("View")[1])
    assert r.texts() == ["✓"]
