from __future__ import annotations

from pyxpo import (Animated, FlatList, Image, ScrollView, SectionList, Text, View, component, use_animated_value,
                   use_ref, use_state)
from pyxpo.components.lists import window_range

from tests.test_core import mount


def test_window_range():
    assert window_range(0, 600, 50, 1000, 3) == (0, 24)
    assert window_range(5000, 600, 50, 1000, 3) == (88, 124)
    assert window_range(0, 600, 50, 5, 3) == (0, 5)


def test_scrollview_content_container_wraps():
    app, r = mount(lambda: ScrollView(Text("a"), contentContainerStyle={"padding": 8}, horizontal=True))
    sv = r.find_all("ScrollView")[0]
    assert sv.props["horizontal"] is True and "content_container_style" not in sv.props
    wrap = sv.children[0]
    assert wrap.type == "View" and wrap.children[0].props["text"] == "a"


def test_scrollview_ref_calls_native():
    holder = {}

    @component
    def App():
        holder["ref"] = use_ref(None)
        return ScrollView(Text("a"), ref=holder["ref"])

    app, r = mount(App)
    sv = r.find_all("ScrollView")[0]
    assert "ref" not in sv.props
    holder["ref"].current.scrollTo({"y": 100, "animated": False})
    holder["ref"].current.scrollToEnd()
    calls = [(c.module, c.method, c.args) for c in r.calls if c.module == "Scroll"]
    assert calls == [("Scroll", "to", [sv.id, 0.0, 100.0, False]), ("Scroll", "to_end", [sv.id, True])]


def test_scrollview_ref_swap_unbinds_old_ref():
    from pyxpo.hooks import Ref
    a, b = Ref(), Ref()
    box = {}

    @component
    def App():
        which, set_which = use_state(0)
        box["set"] = set_which
        return ScrollView(Text("a"), ref=a if which == 0 else b)

    app, r = mount(App)
    assert a.current is not None and b.current is None
    box["set"](1)
    assert a.current is None and b.current is not None


def test_animated_event_native_and_listener():
    holder = {}

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
    app, r = mount(lambda: FlatList(data=data, renderItem=lambda p: Text(p["item"]["t"]), getItemLayout=lambda d, i: {
        "length": 50, "offset": 50 * i, "index": i}, windowSize=3, style={"flex": 1}))
    texts = [n.props["text"] for n in r.find_all("Text")]
    assert texts[0] == "row0" and 10 < len(texts) < 40
    sv = r.find_all("ScrollView")[0]
    r.scroll(sv, y=20000, height=600, width=360, content_height=50000)
    texts = [n.props["text"] for n in r.find_all("Text")]
    assert "row0" not in texts and "row400" in texts and len(texts) < 40


def test_flatlist_batches_and_end_reached():
    hits = []
    app, r = mount(lambda: FlatList(data=list(range(100)), renderItem=lambda p: Text("n%d" % p["item"]),
                                    initialNumToRender=5, maxToRenderPerBatch=10,
                                    onEndReached=lambda info: hits.append(1)))
    assert len(r.find_all("Text")) == 5
    sv = r.find_all("ScrollView")[0]
    r.scroll(sv, y=200, height=640, content_height=700)
    assert len(r.find_all("Text")) == 15 and hits == [1]
    r.scroll(sv, y=210, height=640, content_height=700)
    assert hits == [1]


def test_flatlist_header_footer_empty_separator_columns():
    app, r = mount(lambda: FlatList(
        data=[1, 2, 3], renderItem=lambda p: Text("c%d" % p["item"]), numColumns=2,
        ListHeaderComponent=lambda: Text("H"), ListFooterComponent=Text("F"),
        ItemSeparatorComponent=lambda: Text("-")))
    assert [n.props["text"] for n in r.find_all("Text")] == ["H", "c1", "c2", "-", "c3", "F"]
    app, r = mount(lambda: FlatList(data=[], renderItem=lambda p: Text("x"), ListEmptyComponent=Text("empty")))
    assert [n.props["text"] for n in r.find_all("Text")] == ["empty"]


def test_flatlist_columns_lay_items_out_in_a_row():
    # RN puts num_columns items straight into the row, so a card styled {"flex": 1} grows sideways.
    app, r = mount(lambda: FlatList(data=[1, 2, 3], renderItem=lambda p: View(Text("c%d" % p["item"]), style={"flex": 1}),
                                    numColumns=2))
    cell = r.find_text("c1").parent.parent
    assert cell.props["style"]["flex_direction"] == "row"
    assert cell.parent.props["style"]["flex_direction"] == "row"
    assert len(cell.parent.children) == 2 and len(r.find_text("c3").parent.parent.parent.children) == 2


def test_flatlist_header_and_scroll_in_one_batch():
    app, r = mount(lambda: FlatList(
        data=list(range(1000)), renderItem=lambda p: Text("n%d" % p["item"]),
        getItemLayout=lambda d, i: {"length": 100, "offset": 100 * i, "index": i}, windowSize=1,
        ListHeaderComponent=Text("head")))
    sv = r.find_all("ScrollView")[0]
    head = r.find_text("head").parent
    app.flushing = True  # deliver both events before any re-render, like one native batch
    r.emit("layout", head, {"value": {"x": 0, "y": 0, "width": 360, "height": 5000}})
    r.scroll(sv, y=5000, height=600, content_height=105000)
    app.flushing = False
    app.flush()
    assert "n0" in r.texts() and "n50" not in r.texts()


def test_flatlist_ref_handle_scrolls():
    box = {}

    @component
    def App():
        box["ref"] = use_ref(None)
        return FlatList(data=list(range(100)), renderItem=lambda p: Text(str(p["item"])), ref=box["ref"],
                        getItemLayout=lambda d, i: {"length": 50, "offset": 50 * i, "index": i})

    app, r = mount(App)
    sv = r.find_all("ScrollView")[0]
    box["ref"].current.scrollToIndex({"index": 4, "animated": False})
    c = [c for c in r.calls if c.module == "Scroll"][-1]
    assert c.args == [sv.id, 0.0, 200.0, False]


def test_image_source_normalized():
    el = Image(source="https://x/y.png", style={"width": 10})
    assert el.props["source"] == {"uri": "https://x/y.png"}
    assert Image(source={"uri": "asset:logo"}).props["source"]["uri"] == "asset:logo"
    assert Image(source="pic.png").props["source"]["uri"].endswith("/pic.png")


def test_section_list_rows_keys_and_empty_sections():
    secs = [{"title": "A", "data": [{"id": 1}, {"id": 2}]}, {"title": "B", "data": []}]
    app, r = mount(lambda: SectionList(
        sections=secs, renderItem=lambda p: Text("i%d" % p["item"]["id"]),
        renderSectionHeader=lambda p: Text("h" + p["section"]["title"]),
        renderSectionFooter=lambda p: Text("f" + p["section"]["title"])))
    assert [n.props["text"] for n in r.find_all("Text")] == ["hA", "i1", "i2", "fA", "hB", "fB"]
