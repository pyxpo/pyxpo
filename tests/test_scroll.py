from __future__ import annotations

from pyxpo import (Animated, FlatList, Image, ScrollView, Text, View, component, use_animated_value, use_scroll_ref,
                   use_state)
from pyxpo.scroll import window_range

from .test_core import mount


def test_window_range():
    assert window_range(0, 600, 50, 1000, 3) == (0, 24)
    assert window_range(5000, 600, 50, 1000, 3) == (88, 124)
    assert window_range(0, 600, 50, 5, 3) == (0, 5)


def test_scrollview_content_container_wraps():
    @component
    def App():
        return ScrollView(Text("a"), content_container_style={"padding": 8}, horizontal=True)

    app, r = mount(App)
    sv = r.find_all("ScrollView")[0]
    assert sv.props["horizontal"] is True
    assert "content_container_style" not in sv.props
    wrap = sv.children[0]
    assert wrap.type == "View" and wrap.children[0].props["text"] == "a"


def test_scroll_ref_calls_native():
    holder = {}

    @component
    def App():
        holder["ref"] = use_scroll_ref()
        return ScrollView(Text("a"), ref=holder["ref"])

    app, r = mount(App)
    sv = r.find_all("ScrollView")[0]
    assert "ref" not in sv.props
    holder["ref"].scroll_to(y=100, animated=False)
    holder["ref"].scroll_to_end()
    app.flush() if hasattr(app, "flush") else None
    calls = [(c.module, c.method, c.args) for c in r.calls if c.module == "Scroll"]
    assert calls == [("Scroll", "to", [sv.id, 0.0, 100.0, False]), ("Scroll", "to_end", [sv.id, True])]


def test_animated_event_native_and_listener():
    holder = {}
    seen = []

    @component
    def App():
        y = use_animated_value(0)
        holder["y"] = y
        return ScrollView(Text("a"), on_scroll=Animated.event({"y": y}),
                          style={"opacity": y.interpolate([0, 100], [1, 0])})

    app, r = mount(App)
    sv = r.find_all("ScrollView")[0]
    assert sv.props["on_scroll"]["$ae"] == {"y": holder["y"].id} and sv.props["on_scroll"]["emit"] is False
    r.scroll(sv, y=50)
    assert abs(r.resolved(sv, "opacity") - 0.5) < 1e-6


def test_animated_event_python_fallback_and_rn_form():
    holder = {}
    seen = []

    @component
    def App():
        y = use_animated_value(0)
        holder["y"] = y
        ev = Animated.event([{"native_event": {"content_offset": {"y": y}}}], listener=seen.append,
                            use_native_driver=False)
        return ScrollView(Text("a"), on_scroll=ev)

    app, r = mount(App)
    sv = r.find_all("ScrollView")[0]
    assert sv.props["on_scroll"] is True
    r.scroll(sv, y=70)
    assert holder["y"].get_value() == 70 and seen and seen[0]["y"] == 70


def test_flatlist_windows_fixed_rows():
    data = [{"id": i, "t": "row%d" % i} for i in range(1000)]

    @component
    def App():
        return FlatList(data=data, render_item=lambda it, i: Text(it["t"]), item_size=50, window_size=3,
                        style={"flex": 1})

    app, r = mount(App)
    texts = [n.props["text"] for n in r.find_all("Text")]
    assert texts[0] == "row0" and 10 < len(texts) < 40
    sv = r.find_all("ScrollView")[0]
    r.scroll(sv, y=20000, height=600, width=360, content_height=50000)
    texts = [n.props["text"] for n in r.find_all("Text")]
    assert "row0" not in texts and "row400" in texts and len(texts) < 40


def test_flatlist_batches_and_end_reached():
    data = list(range(100))
    hits = []

    @component
    def App():
        return FlatList(data=data, render_item=lambda it, i: Text("n%d" % it), initial_num_to_render=5,
                        batch_size=10, on_end_reached=lambda: hits.append(1))

    app, r = mount(App)
    assert len(r.find_all("Text")) == 5
    sv = r.find_all("ScrollView")[0]
    r.scroll(sv, y=200, height=640, content_height=700)
    assert len(r.find_all("Text")) == 15 and hits == [1]
    r.scroll(sv, y=210, height=640, content_height=700)
    assert hits == [1]


def test_flatlist_header_footer_empty_columns():
    @component
    def App():
        return FlatList(data=[1, 2, 3], render_item=lambda it, i: Text("c%d" % it), num_columns=2,
                        list_header_component=lambda: Text("H"), list_footer_component=Text("F"),
                        item_separator=lambda: Text("-"))

    app, r = mount(App)
    texts = [n.props["text"] for n in r.find_all("Text")]
    assert texts == ["H", "c1", "c2", "-", "c3", "F"]

    @component
    def E():
        return FlatList(data=[], render_item=lambda it, i: Text("x"), list_empty_component=Text("empty"))

    app, r = mount(E)
    assert [n.props["text"] for n in r.find_all("Text")] == ["empty"]


def test_image_source_normalized():
    el = Image(source="https://x/y.png", style={"width": 10})
    assert el.props["source"] == {"uri": "https://x/y.png"}
    assert Image(source={"uri": "asset:logo"}).props["source"]["uri"] == "asset:logo"
    assert Image(source="pic.png").props["source"]["uri"].endswith("/pic.png")


def test_flatlist_header_and_scroll_in_one_batch():
    data = list(range(1000))

    @component
    def App():
        return FlatList(data=data, render_item=lambda it, i: Text("n%d" % it), item_size=100, window_size=1,
                        list_header_component=Text("head"))

    app, r = mount(App)
    sv = r.find_all("ScrollView")[0]
    head = r.find_text("head").parent
    app.flushing = True  # deliver both events before any re-render, like one native batch
    r.emit("layout", head, {"value": {"x": 0, "y": 0, "width": 360, "height": 5000}})
    r.scroll(sv, y=5000, height=600, content_height=105000)
    app.flushing = False
    app.flush()
    # The header fills the first 5000 dp, so the list window starts at row 0; a lost head update
    # would place the window around row 50.
    assert "n0" in r.texts() and "n50" not in r.texts()


def test_scroll_ref_swap_unbinds_old_ref():
    from pyxpo.scroll import ScrollRef
    a, b = ScrollRef(), ScrollRef()
    box = {}

    @component
    def App():
        which, set_which = use_state(0)
        box["set"] = set_which
        return ScrollView(Text("a"), ref=a if which == 0 else b)

    app, r = mount(App)
    sv = r.find_all("ScrollView")[0]
    assert a.id == sv.id
    box["set"](1)
    assert a.id is None and b.id == sv.id


def test_flatlist_render_item_arity():
    from pyxpo.scroll import adapt_render_item
    assert adapt_render_item(lambda p: (p["item"], p["index"]))("a", 3) == ("a", 3)
    assert adapt_render_item(lambda item, index: (item, index))("a", 3) == ("a", 3)
    assert adapt_render_item(lambda item, index=0, *r: (item, index))("a", 3) == ("a", 3)

    import functools

    def deco(fn):
        @functools.wraps(fn)
        def w(*a, **k):
            return fn(*a, **k)
        return w

    # a decorated one-argument renderer keeps the RN `{"item", "index"}` form
    assert adapt_render_item(deco(lambda p: (p["item"], p["index"])))("a", 3) == ("a", 3)
    assert adapt_render_item(deco(lambda item, index: (item, index)))("a", 3) == ("a", 3)


def test_flatlist_accepts_rn_ref():
    from pyxpo.scroll import ScrollRef
    ref = ScrollRef()
    app, r = mount(lambda: FlatList(data=[1, 2], renderItem=lambda p: Text(str(p["item"])), ref=ref))
    assert r.texts() == ["1", "2"] and ref.id == r.find_all("ScrollView")[0].id


def test_section_list_rows_keys_and_empty_sections():
    from pyxpo import SectionList, Text
    from pyxpo.scroll import FlatList
    secs = [{"title": "A", "data": [{"id": 1}, {"id": 2}]}, {"title": "B", "data": []}]
    @component
    def App():
        return SectionList(sections=secs, render_item=lambda p: Text("i%d" % p["item"]["id"]),
                           render_section_header=lambda p: Text("h" + p["section"]["title"]),
                           render_section_footer=lambda p: Text("f" + p["section"]["title"]))

    app, r = mount(App)
    texts = [n.props["text"] for n in r.find_all("Text")]
    assert texts == ["hA", "i1", "i2", "fA", "hB", "fB"]
