from __future__ import annotations

import time

from pyxpo import Button, FlatList, ThemeProvider, Text, View, component, dark_theme, light_theme, memo, use_state, use_theme

from .test_core import mount


def test_memo_skips_equal_props_and_rerenders_on_change():
    renders = []

    @component
    def Row(label="", n=0):
        renders.append(label)
        return Text(label)

    MRow = memo(Row)
    box = {}

    @component
    def App():
        n, set_n = use_state(0)
        box["set"] = set_n
        return View(MRow(label="a"), MRow(label="b" if n < 2 else "c"), Text("n=%d" % n))

    app, r = mount(lambda: App())
    assert renders == ["a", "b"]
    box["set"](1)
    app.flush() if hasattr(app, "flush") else None
    assert renders == ["a", "b"]
    assert "n=1" in r.texts()
    box["set"](2)
    app.flush() if hasattr(app, "flush") else None
    assert renders == ["a", "b", "c"]


def test_memo_does_not_block_context_updates():
    seen = []

    @component
    def Probe():
        seen.append(use_theme()["dark"])
        return Text("p")

    MProbe = memo(Probe)
    box = {}

    @component
    def App():
        d, set_d = use_state(False)
        box["set"] = set_d
        return ThemeProvider(MProbe(), theme=dark_theme if d else light_theme)

    app, r = mount(lambda: App())
    assert seen == [False]
    box["set"](True)
    app.flush() if hasattr(app, "flush") else None
    assert seen == [False, True]


def test_sync_large_list_append_and_reorder_fast():
    box = {}

    @component
    def App():
        items, set_items = use_state(list(range(2000)))
        box["set"] = set_items
        return View(*[Text(str(i), key=i) for i in items])

    app, r = mount(lambda: App())
    t = time.time()
    box["set"](list(range(2000, -1, -1)))
    app.flush() if hasattr(app, "flush") else None
    assert [n.props["text"] for n in r.root.children[0].children][:2] == ["2000", "1999"]
    assert time.time() - t < 5
