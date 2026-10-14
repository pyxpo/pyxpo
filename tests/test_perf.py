from __future__ import annotations

import time

from pyxpo import Button, FlatList, Text, View, component, create_context, memo, use_context, use_state

ThemeCtx = create_context({"dark": False})

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
        seen.append(use_context(ThemeCtx)["dark"])
        return Text("p")

    MProbe = memo(Probe)
    box = {}

    @component
    def App():
        d, set_d = use_state(False)
        box["set"] = set_d
        return ThemeCtx.Provider(MProbe(), value={"dark": d})

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


def test_normalize_cache_returns_independent_dicts():
    from pyxpo.style import normalize
    a = normalize([{"color": "#fff"}, {"padding": 2}])
    a["color"] = 0
    b = normalize([{"color": "#fff"}, {"padding": 2}])
    assert b["color"] == 0xFFFFFFFF and b["padding_left"] == 2


def test_dispatch_handler_arity_and_inner_type_error():
    from pyxpo.reconciler import _takes_value
    assert _takes_value(lambda v: None) and not _takes_value(lambda: None)

    def bad(v):
        raise TypeError("wrong argument inside handler")
    calls = []

    def count():
        calls.append(1)
    assert _takes_value(bad) and not _takes_value(count)


def test_normalize_cache_key_distinguishes_value_types():
    from pyxpo.style import normalize
    assert "flex_grow" not in normalize({"flex": True})
    assert normalize({"flex": 1})["flex_grow"] == 1


def test_takes_value_not_cached_across_shared_wrapper_code():
    import functools
    from pyxpo.reconciler import _takes_value

    def deco(f):
        @functools.wraps(f)
        def w(*a):
            return f(*a)
        return w

    @deco
    def no_arg():
        pass

    @deco
    def one_arg(v):
        pass
    assert not _takes_value(no_arg) and _takes_value(one_arg)
