from __future__ import annotations

import json

from pyxpo import (component, AppButton, Card, Field, ProgressBar, Stack, Text, ThemeProvider, Typography, create_theme,
                   dark_theme, light_theme, use_theme)

from .test_core import mount


def _style(n):
    from pyxpo.style import flatten
    return flatten(n.props.get("style"))


def test_create_theme_deep_merge():
    t = create_theme(light_theme, colors={"primary": "#ff0000"}, text={"body": {"font_size": 20}})
    assert t["colors"]["primary"] == "#ff0000" and t["colors"]["surface"] == light_theme["colors"]["surface"]
    assert t["text"]["body"]["font_size"] == 20 and t["text"]["body"].get("font_weight") is None
    assert light_theme["colors"]["primary"] == "#1a73e8" and light_theme["text"]["body"]["font_size"] == 15


def test_use_theme_default_and_provider_modes():
    seen = []

    @component
    def Probe():
        seen.append(use_theme()["dark"])
        return Text("x")

    mount(lambda: ThemeProvider(Probe()))
    assert seen[-1] is False
    mount(lambda: ThemeProvider(Probe(), mode="dark"))
    assert seen[-1] is True
    mount(lambda: ThemeProvider(Probe(), theme=dark_theme, mode="light"))
    assert seen[-1] is True


def test_system_mode_follows_os_scheme():
    seen = []

    @component
    def Probe():
        seen.append(use_theme()["dark"])
        return Text("x")

    app, r = mount(lambda: ThemeProvider(Probe()))
    assert seen[-1] is False
    r.channel.emit_event(json.dumps({"event": "env", "id": 0, "payload": {"color_scheme": "dark"}}))
    assert seen[-1] is True


def test_kit_components_use_theme_colors():
    app, r = mount(lambda: ThemeProvider(
        Card(Typography("hi", variant="title"), AppButton(label="Go", tone="danger"), ProgressBar(value=2, native=False)),
        mode="dark"))
    d = dark_theme["colors"]
    t = r.find_text("hi")
    assert _style(t)["color"] == d["text"] and _style(t)["font_size"] == 28
    go = r.find_text("Go")
    assert _style(go)["color"] == d["on_danger"]
    assert _style(go.parent)["background_color"] == d["danger"]
    bar = [n for n in r.root.walk() if _style(n).get("width") == "100%"]
    assert bar


def test_field_error_state():
    app, r = mount(lambda: Field(label="Name", error="Required", value=""))
    assert "Name" in r.texts() and "Required" in r.texts()
    assert _style(r.find_all("TextInput")[0])["border_color"] == light_theme["colors"]["danger"]


def test_navigation_header_follows_theme():
    app, r = mount(lambda: ThemeProvider(Stack(screens={"Home": lambda navigation, params: Text("h")}), mode="dark"))
    title = r.find_text("Home")
    assert _style(title)["color"] == dark_theme["colors"]["text"]


def test_screen_scroll_applies_style_to_content():
    from pyxpo.kit import Screen
    app, r = mount(lambda: Screen(Text("x"), scroll=True, style={"background_color": "#123456"}))
    content = r.find_text("x").parent
    assert content.props["style"]["background_color"] == "#123456"
