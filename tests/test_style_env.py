from __future__ import annotations

import json

import pytest

import pyxpo
from pyxpo import StyleSheet, Text, View, component, parse_color
from pyxpo.channel import LocalChannel
from pyxpo.env import breakpoint_for, responsive
from pyxpo.style import StyleError, normalize


def test_colors():
    assert parse_color("#fff") == 0xFFFFFFFF
    assert parse_color("#11223344") == 0x44112233
    assert parse_color("rgba(255, 0, 0, 0.5)") == 0x80FF0000
    assert parse_color("red") == 0xFFFF0000
    assert parse_color((0, 0, 255)) == 0xFF0000FF
    with pytest.raises(StyleError):
        parse_color("#12")


def test_flatten_and_expand():
    s = normalize([{"padding": 8, "padding_left": 2}, None, False, {"margin_vertical": 4, "gap": 3}])
    assert s["padding_top"] == 8 and s["padding_left"] == 2
    assert s["margin_top"] == 4 and s["margin_bottom"] == 4
    assert s["row_gap"] == 3 and s["column_gap"] == 3
    f = normalize({"flex": 1})
    assert f["flex_grow"] == 1 and f["flex_shrink"] == 1 and f["flex_basis"] == 0
    assert normalize({"background_color": "#000"})["background_color"] == 0xFF000000


def test_stylesheet_validates():
    ss = StyleSheet.create({"a": {"padding": 4}})
    assert ss["a"] == {"padding": 4}
    with pytest.raises(StyleError):
        StyleSheet.create({"a": {"color": "nope"}})


def test_breakpoints():
    assert breakpoint_for(320) == "sm" and breakpoint_for(600) == "md" and breakpoint_for(900) == "lg"
    assert responsive("lg", {"sm": 1, "md": 2}) == 2
    assert responsive("sm", {"md": 2}, 9) == 9


def _texts(ch):
    out = []
    for batch in ch.sent:
        for o in json.loads(batch):
            if o["op"] == "create" and o["type"] == "Text":
                out.append(o["props"]["text"])
            if o["op"] == "update" and "text" in o["props"]:
                out.append(o["props"]["text"])
    return out


def test_env_hooks_rerender_and_style_list():
    @component
    def App():
        w = pyxpo.use_window_dimensions()
        bp = pyxpo.use_breakpoint()
        dark = pyxpo.use_color_scheme() == "dark"
        return View(Text("%d %s %s" % (w["width"], bp, dark)), style=[{"padding": 1}, {"flex": 1}])

    ch = LocalChannel()
    ch.sent = []
    ch.set_native_handler(ch.sent.append)
    app = pyxpo.create_app(App, ch)
    assert _texts(ch)[-1] == "360 sm False"
    first = json.loads(ch.sent[0])
    assert [o for o in first if o["op"] == "create" and o["type"] == "View"][0]["props"]["style"]["padding_left"] == 1
    ch_msg = json.dumps({"event": "env", "id": 0, "payload": {"window": {"width": 700}, "color_scheme": "dark"}})
    ch.emit_event(ch_msg)
    assert _texts(ch)[-1] == "700 md True"
    assert pyxpo.Dimensions.get("window")["width"] == 700
    n = len(ch.sent)
    ch.emit_event(ch_msg)  # no change: no extra batch
    assert len(ch.sent) == n


def test_platform_select():
    assert pyxpo.Platform.select({"android": 1, "default": 2}) == 2
    assert pyxpo.PixelRatio.round_to_nearest_pixel(1.3) == 1.0


def test_wire_v2_normalizes_style(monkeypatch):
    monkeypatch.setenv("PYXPO_ENV", '{"window": {"width": 412, "height": 900}, "scale": 2.5}')
    from pyxpo import View, Text
    from pyxpo.app import App
    from pyxpo.channel import LocalChannel
    ch = LocalChannel()
    ch.sent = []
    ch.set_native_handler(ch.sent.append)
    app = App(View(style=[{"padding": 4}, {"background_color": "#ff0000"}]), ch)
    app.start()
    assert app.env.get()["window"]["width"] == 412 and app.env.get()["scale"] == 2.5
    import json
    ops = [o for batch in ch.sent for o in json.loads(batch)]
    st = [o for o in ops if o["op"] == "create"][0]["props"]["style"]
    assert st["background_color"] == 0xFFFF0000 and st["padding_left"] == 4 and "padding" not in st


def test_linear_gradient_normalized():
    from pyxpo.style import StyleError, normalize
    g = normalize({"linear_gradient": {"angle": 90, "colors": ["red", "#0000ff"]}})["linear_gradient"]
    assert g == {"angle": 90.0, "colors": [0xFFFF0000, 0xFF0000FF], "stops": [0.0, 1.0]}
    import pytest
    with pytest.raises(StyleError):
        normalize({"linear_gradient": {"colors": ["red"]}})


def test_normalize_cache_shared_vs_copy():
    from pyxpo.style import normalize_shared
    s = {"padding": 4, "opacity": 1}
    a, b = normalize_shared(s), normalize_shared(dict(s))
    assert a is b  # equal content hits one cached dict
    c = normalize(s)
    assert c == a and c is not a  # public normalize hands out a private copy
    c["padding_left"] = 99
    assert normalize_shared(s)["padding_left"] == 4
    # 1, 1.0 and True compare equal but must not share a cache entry
    assert normalize_shared({"flex": 1}) is not normalize_shared({"flex": 1.0})
    assert normalize_shared({"flex": True}) is not normalize_shared({"flex": 1})
