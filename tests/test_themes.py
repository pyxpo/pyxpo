"""Themed StyleSheets (`StyleSheet.configure` + `StyleSheet.create(lambda theme, rt: ...)`), dynamic styles and
`useAppTheme`."""
from __future__ import annotations

import json

import pytest

import pyxpo
from pyxpo import StyleSheet, Text, View, component, responsive, themes, use_app_theme
from pyxpo.channel import LocalChannel
from pyxpo.style import StyleError, parse_color

LIGHT = {"colors": {"bg": "#ffffff", "text": "#111111"}}
DARK = {"colors": {"bg": "#000000", "text": "#eeeeee"}}


@pytest.fixture(autouse=True)
def _reset():
    yield
    themes._themes, themes._adaptive, themes._chosen = {}, True, None
    themes._listeners.clear()
    responsive.set_breakpoints()


def _app(root):
    ch = LocalChannel()
    ch.sent = []
    ch.set_native_handler(ch.sent.append)
    return pyxpo.create_app(root, ch), ch


def env(ch, **payload):
    ch.emit_event(json.dumps({"event": "env", "id": 0, "payload": payload}))


def _ops(ch, start=0):
    return [o for b in ch.sent[start:] for o in json.loads(b)]


def _style(ch, tid):
    """Latest style sent for the view with test_id `tid`."""
    nid, style = None, None
    for o in _ops(ch):
        if o["op"] == "create" and o["props"].get("test_id") == tid:
            nid = o["id"]
        if nid is not None and o["id"] == nid and "style" in o.get("props", {}):
            style = o["props"]["style"]
    return style


styles = StyleSheet.create(lambda theme, rt: {
    "screen": {"flex": 1, "backgroundColor": theme.colors.bg, "paddingTop": rt.insets.top},
    "title": {"color": theme["colors"]["text"], "fontSize": {"base": 16, "md": 24}},
    "box": lambda size: {"width": size, "height": size},
})


@component
def Screen():
    return View(Text("hi", style=styles.title, testID="title"), View(style=[styles.box(40), {"opacity": 0.5}], testID="box"),
                style=styles.screen, testID="screen")


def test_theme_follows_color_scheme_without_rerender():
    StyleSheet.configure(themes={"light": LIGHT, "dark": DARK})
    renders = []

    @component
    def Root():
        renders.append(1)
        return Screen()

    app, ch = _app(Root)
    assert _style(ch, "screen")["background_color"] == parse_color("#ffffff")
    assert _style(ch, "title")["color"] == parse_color("#111111")
    n = len(renders)
    start = len(ch.sent)
    env(ch, color_scheme="dark")
    assert _style(ch, "screen")["background_color"] == parse_color("#000000")
    assert _style(ch, "title")["color"] == parse_color("#eeeeee")
    assert len(renders) == n  # re-styled, not re-rendered
    assert all(o["op"] == "update" for o in _ops(ch, start))


def test_set_theme_and_adaptive():
    StyleSheet.configure(themes={"light": LIGHT, "dark": DARK})
    app, ch = _app(Screen)
    StyleSheet.setTheme("dark")
    assert _style(ch, "screen")["background_color"] == parse_color("#000000")
    env(ch, color_scheme="light")  # not adaptive anymore
    assert _style(ch, "screen")["background_color"] == parse_color("#000000")
    StyleSheet.setAdaptiveThemes(True)
    assert _style(ch, "screen")["background_color"] == parse_color("#ffffff")
    with pytest.raises(ValueError):
        StyleSheet.setTheme("nope")


def test_rt_insets_breakpoints_and_dynamic_style():
    StyleSheet.configure(themes={"light": LIGHT})
    app, ch = _app(Screen)
    assert _style(ch, "screen")["padding_top"] == 0
    assert _style(ch, "title")["font_size"] == 16
    assert _style(ch, "box")["width"] == 40 and _style(ch, "box")["opacity"] == 0.5
    env(ch, insets={"top": 47, "right": 0, "bottom": 34, "left": 0})
    assert _style(ch, "screen")["padding_top"] == 47
    env(ch, window={"width": 900, "height": 800})
    assert _style(ch, "title")["font_size"] == 24


def test_initial_theme_and_non_adaptive():
    StyleSheet.configure(themes={"light": LIGHT, "dark": DARK}, adaptiveThemes=False, initialTheme="dark")
    app, ch = _app(Screen)
    assert _style(ch, "screen")["background_color"] == parse_color("#000000")


def test_themed_style_works_as_plain_dict():
    StyleSheet.configure(themes={"light": LIGHT, "dark": DARK})
    assert styles.screen["backgroundColor"] == "#ffffff"
    assert {**styles.title}["color"] == "#111111"
    assert StyleSheet.flatten([styles.screen, {"flex": 2}])["flex"] == 2
    assert styles.box(10) == {"width": 10, "height": 10}
    with pytest.raises(AttributeError):
        styles.missing


def test_one_arg_factory_and_theme_attribute_errors():
    StyleSheet.configure(themes={"light": LIGHT})
    s = StyleSheet.create(lambda theme: {"a": {"color": theme.colors.text}})
    assert s.a["color"] == "#111111"
    bad = StyleSheet.create(lambda theme: {"a": {"color": theme.colors.nope}})
    with pytest.raises(AttributeError, match="nope"):
        bad.a


def test_plain_create_dynamic_entries_validate():
    s = StyleSheet.create({"box": lambda n: {"width": n}, "card": {"padding": 4}})
    assert s.box(3) == {"width": 3} and s.card == {"padding": 4}
    bad = StyleSheet.create({"box": lambda n: {"color": n}})
    with pytest.raises(StyleError):
        bad.box("not-a-color")


def test_configure_breakpoints():
    StyleSheet.configure(themes={"light": LIGHT}, breakpoints={"phone": 0, "tablet": 600})
    assert responsive.breakpoint_for(700) == "tablet"


def test_use_app_theme_rerenders():
    StyleSheet.configure(themes={"light": LIGHT, "dark": DARK})
    seen = []

    @component
    def Root():
        t = use_app_theme()
        seen.append(t.colors.bg)
        return View()

    app, ch = _app(Root)
    env(ch, color_scheme="dark")
    StyleSheet.setTheme("light")
    assert seen[0] == "#ffffff" and "#000000" in seen and seen[-1] == "#ffffff"
