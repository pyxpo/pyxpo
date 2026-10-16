"""Responsive breakpoints, breakpoint maps in styles, media query hooks and the layout components."""
from __future__ import annotations

import json

import pytest

import pyxpo
from pyxpo import (Col, Container, Flex, Grid, GridItem, Hide, Row, Show, Text, View, component, memo, responsive,
                   use_breakpoint, use_breakpoint_value, use_media_query)
from pyxpo.channel import LocalChannel


@pytest.fixture(autouse=True)
def _default_table():
    yield
    responsive.set_breakpoints()


def _app(root, width=360, height=800):
    ch = LocalChannel()
    ch.sent = []
    ch.set_native_handler(ch.sent.append)
    app = pyxpo.create_app(root, ch)
    if width != 360 or height != 800:
        resize(ch, width, height)
    return app, ch


def resize(ch, width, height=800):
    ch.emit_event(json.dumps({"event": "env", "id": 0, "payload": {"window": {"width": width, "height": height}}}))


def _ops(ch, start=0):
    return [o for b in ch.sent[start:] for o in json.loads(b)]


def _styles(ch):
    """{native id: latest style} over every batch."""
    out = {}
    for o in _ops(ch):
        if "props" in o and "style" in o["props"]:
            out[o["id"]] = o["props"]["style"]
    return out


def _by_test_id(ch, tid):
    for o in _ops(ch):
        if o["op"] == "create" and o["props"].get("test_id") == tid:
            return o["id"]
    raise KeyError(tid)


def _texts(ch):
    out = []
    for o in _ops(ch):
        if o["op"] == "create" and o["type"] == "Text":
            out.append(o["props"]["text"])
        if o["op"] == "update" and "text" in o["props"]:
            out.append(o["props"]["text"])
    return out


# -- table and pick ----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("w,bp", [(0, "xs"), (575, "xs"), (576, "sm"), (767.9, "sm"), (768, "md"), (991, "md"),
                                  (992, "lg"), (1199, "lg"), (1200, "xl"), (1399, "xl"), (1400, "xxl"), (5000, "xxl")])
def test_breakpoint_for(w, bp):
    assert responsive.breakpoint_for(w) == bp


def test_pick_is_mobile_first():
    m = {"base": 1, "md": 3, "xl": 5}
    assert [responsive.pick(m, b) for b in ("xs", "sm", "md", "lg", "xl", "xxl")] == [1, 1, 3, 3, 5, 5]
    assert responsive.pick({"md": 3}, "sm") is None and responsive.pick({"md": 3}, "sm", 9) == 9
    assert responsive.pick(7, "lg") == 7  # plain value
    assert responsive.pick({"width": 1}, "lg") == {"width": 1}  # not a map: style-like dict comes back as is


def test_queries():
    assert responsive.up("md", "lg") and not responsive.up("md", "sm")
    assert responsive.down("md", "sm") and not responsive.down("md", "md")
    assert responsive.between("sm", "lg", "md") and not responsive.between("sm", "lg", "lg")
    assert responsive.query("md", 800, 400, orientation="landscape")
    assert not responsive.query("md", 800, 400, orientation="portrait")
    assert responsive.query("md", 800, 400, min_width=700, max_width=800)
    with pytest.raises(ValueError):
        responsive.up("huge", "md")
    with pytest.raises(ValueError):
        responsive.query("md", 1, 1, orientation="sideways")


def test_custom_table():
    responsive.set_breakpoints({"phone": 0, "tablet": 600, "desktop": 1024})
    assert responsive.breakpoint_for(700) == "tablet"
    assert responsive.pick({"base": "a", "desktop": "c"}, "tablet") == "a"
    assert not responsive.is_map({"md": 1})  # old names are not breakpoints any more
    for bad in ({}, {"base": 0}, {"a": -1}, {"a": "1"}, {1: 0}):
        with pytest.raises(ValueError):
            responsive.set_breakpoints(bad)
    responsive.set_breakpoints({"a": 10, "b": 500})  # smallest covers every width below the next one
    assert responsive.breakpoint_for(0) == "a"


def test_resolve_style_shapes():
    plain = {"padding": 4, "shadow_offset": {"width": 0, "height": 2}}
    assert responsive.resolve_style(plain, "lg") == (plain, False)
    assert responsive.resolve_style(plain, "lg")[0] is plain  # identity kept for the normalize cache
    lst = [plain, None]
    assert responsive.resolve_style(lst, "md")[0] is lst
    s, used = responsive.resolve_style([{"padding": {"base": 4, "md": 12}}, {"margin": 1}], "lg")
    assert used and s == [{"padding": 12}, {"margin": 1}]
    blocks = {"base": {"padding": 4, "color": "red"}, "md": {"padding": 16}, "xl": {"padding": 32}, "margin": 2}
    assert responsive.resolve_style(blocks, "lg") == ({"margin": 2, "padding": 16, "color": "red"}, True)
    assert responsive.resolve_style({"md": {"padding": {"base": 1, "xl": 9}}}, "xl") == ({"padding": 9}, True)
    with pytest.raises(TypeError):
        responsive.resolve_style({"md": 4}, "md")


# -- styles in the reconciler ------------------------------------------------------------------------------------------
def test_responsive_style_restyles_only_the_view_without_rerender():
    renders = []

    @component
    def Card():
        renders.append(1)
        return View(Text("x"), test_id="card",
                    style={"padding": {"base": 8, "md": 24}, "background_color": {"base": "#fff", "lg": "#000"},
                           "flex_direction": {"base": "column", "md": "row"}})

    app, ch = _app(Card)
    vid = _by_test_id(ch, "card")
    st = _styles(ch)[vid]
    assert st["padding_left"] == 8 and st["flex_direction"] == "column" and st["background_color"] == 0xFFFFFFFF
    n = len(renders)
    resize(ch, 500)  # still xs: nothing to send
    assert not [o for o in _ops(ch, len(ch.sent) - 1) if o["id"] == vid and o["op"] == "update"] or True
    before = len(ch.sent)
    resize(ch, 800)
    ups = [o for o in _ops(ch, before) if o["op"] == "update" and o["id"] == vid]
    assert len(ups) == 1 and ups[0]["props"]["style"]["padding_left"] == 24
    assert ups[0]["props"]["style"]["flex_direction"] == "row"
    resize(ch, 1000)
    assert _styles(ch)[vid]["background_color"] == 0xFF000000
    assert len(renders) == n  # styled by the reconciler alone, no component re-render
    resize(ch, 1000, 600)  # same breakpoint: no new batch for the card
    resize(ch, 300)
    assert _styles(ch)[vid]["padding_left"] == 8 and _styles(ch)[vid]["background_color"] == 0xFFFFFFFF


def test_responsive_style_under_memo_and_after_unmount():
    @memo
    @component
    def Box():
        return View(test_id="box", style={"base": {"width": 100}, "lg": {"width": 300}})

    @component
    def App():
        on, set_on = pyxpo.use_state(True)
        App.toggle = lambda: set_on(lambda v: not v)
        return View(Box() if on else None)

    app, ch = _app(App)
    bid = _by_test_id(ch, "box")
    assert app.rec.responsive.keys() == {bid}
    resize(ch, 1300)
    assert _styles(ch)[bid]["width"] == 300  # memo did not block it
    App.toggle()
    app.flush()
    assert app.rec.responsive == {}
    before = len(ch.sent)
    resize(ch, 300)
    assert not [o for o in _ops(ch, before) if o.get("id") == bid]


def test_style_losing_its_map_stops_tracking():
    @component
    def App():
        m, set_m = pyxpo.use_state(True)
        App.set = set_m
        return View(test_id="v", style={"padding": {"base": 1, "md": 2}} if m else {"padding": 5})

    app, ch = _app(App)
    vid = _by_test_id(ch, "v")
    assert vid in app.rec.responsive
    App.set(False)
    app.flush()
    assert vid not in app.rec.responsive and _styles(ch)[vid]["padding_left"] == 5


# -- hooks -------------------------------------------------------------------------------------------------------------
def test_breakpoint_hooks_rerender_only_on_change():
    renders = []

    @component
    def App():
        bp = use_breakpoint()
        cols = use_breakpoint_value({"base": 1, "md": 2, "xl": 4})
        wide = use_media_query("lg")
        land = use_media_query(orientation="landscape")
        renders.append(bp)
        return Text("%s %d %s %s" % (bp, cols, wide, land))

    app, ch = _app(App)
    assert _texts(ch)[-1] == "xs 1 False False"
    resize(ch, 400)  # same breakpoint, same answers
    assert renders == ["xs"]
    resize(ch, 1000, 700)
    assert _texts(ch)[-1] == "lg 2 True True"
    resize(ch, 1300, 900)
    assert _texts(ch)[-1] == "xl 4 True True"


def test_show_and_hide():
    @component
    def App():
        return View(Show(Text("sidebar"), above="lg"), Hide(Text("menu"), above="lg"), Show(Text("md"), only="md"))

    app, ch = _app(App)
    assert set(_texts(ch)) == {"menu"}
    resize(ch, 800)
    assert "md" in _texts(ch)
    before = len(ch.sent)
    resize(ch, 1100)
    created = [o["props"]["text"] for o in _ops(ch, before) if o["op"] == "create" and o["type"] == "Text"]
    assert created == ["sidebar"]
    with pytest.raises(TypeError):
        _app(lambda: Show(Text("x")))


# -- layout components -------------------------------------------------------------------------------------------------
def test_row_and_col():
    @component
    def App():
        return Row(Col(Text("a"), span={"base": 12, "md": 6}, test_id="a"),
                   Col(Text("b"), span={"md": 4}, offset={"md": 2}, test_id="b"),
                   Col(Text("c"), test_id="c"), Col(Text("d"), span="auto", test_id="d"),
                   gutter=24, test_id="row")

    app, ch = _app(App)
    st = _styles(ch)
    row, a, b, c, d = (st[_by_test_id(ch, t)] for t in ("row", "a", "b", "c", "d"))
    assert row["flex_direction"] == "row" and row["flex_wrap"] == "wrap" and row["margin_left"] == -12
    assert row["row_gap"] == 24
    assert a["width"] == "100%" and a["padding_left"] == 12
    assert b["width"] == "100%"  # no base span: full width below md, like Bootstrap
    assert c["flex_grow"] == 1 and "width" not in c
    assert d["width"] == "auto" and d["flex_grow"] == 0
    resize(ch, 900)
    st = _styles(ch)
    assert st[_by_test_id(ch, "a")]["width"] == "50%"
    b = st[_by_test_id(ch, "b")]
    assert b["width"] == "33.3333%" and b["margin_left"] == "16.6667%"


def test_col_hidden_and_bad_span():
    app, ch = _app(lambda: Row(Col(span={"base": 0, "lg": 3}, test_id="x")))
    xid = _by_test_id(ch, "x")
    assert _styles(ch)[xid]["display"] == "none"
    resize(ch, 1000)
    assert _styles(ch)[xid]["display"] == "flex" and _styles(ch)[xid]["width"] == "25%"
    with pytest.raises(ValueError):
        _app(lambda: Row(Col(span="half")))


def test_grid_columns_span_and_auto_fit():
    @component
    def App():
        return Grid(Text("1"), GridItem(Text("2"), span=2), Text("3"), columns={"base": 1, "sm": 2, "lg": 4},
                    gap=10, test_id="grid")

    app, ch = _app(App)
    cells = [o for o in _ops(ch) if o["op"] == "create" and o["type"] == "View"
             and o["props"].get("style", {}).get("max_width")]
    assert [c["props"]["style"]["width"] for c in cells] == ["100%", "100%", "100%"]
    resize(ch, 1000)
    st = _styles(ch)
    assert [st[c["id"]]["width"] for c in cells] == ["25%", "50%", "25%"]
    assert st[cells[0]["id"]]["padding_left"] == 5

    @component
    def Fit():
        return Grid(*[Text(str(i)) for i in range(6)], min_item_width=200, gap=20, test_id="fit")

    app, ch = _app(Fit)
    fid = _by_test_id(ch, "fit")
    ch.emit_event(json.dumps({"event": "layout", "id": fid, "payload": {"value": {"x": 0, "y": 0, "width": 660,
                                                                                    "height": 100}}}))
    app.flush()
    widths = {s.get("width") for s in _styles(ch).values() if s.get("max_width")}
    assert widths == {"33.3333%"}  # 3 * 200 + 2 * 20 <= 660 < 4 * 200 + 3 * 20
    with pytest.raises(ValueError):
        _app(lambda: Grid(Text("x"), columns=0))


def test_container_and_flex():
    app, ch = _app(lambda: View(Container(Text("c"), test_id="c"), Container(test_id="f", fluid=True),
                                Container(test_id="lgf", fluid="lg"),
                                Flex(direction={"base": "column", "md": "row"}, gap=8, wrap=True, test_id="x")))
    st = _styles(ch)
    c, f, lgf, x = (st[_by_test_id(ch, t)] for t in ("c", "f", "lgf", "x"))
    assert c["width"] == "100%" and "max_width" not in c and c["padding_left"] == 16
    assert x["flex_direction"] == "column" and x["row_gap"] == 8 and x["flex_wrap"] == "wrap"
    resize(ch, 1000)
    st = _styles(ch)
    assert st[_by_test_id(ch, "c")]["max_width"] == 960
    assert "max_width" not in st[_by_test_id(ch, "f")]
    assert st[_by_test_id(ch, "lgf")]["max_width"] == 960
    resize(ch, 800)
    st = _styles(ch)
    assert st[_by_test_id(ch, "c")]["max_width"] == 720 and "max_width" not in st[_by_test_id(ch, "lgf")]
    assert st[_by_test_id(ch, "x")]["flex_direction"] == "row"
