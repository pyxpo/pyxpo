from __future__ import annotations

import pytest

from pyxpo import (Button, HookError, LocalChannel, Text, View, component, create_app, create_context,
                  use_callback, use_context, use_effect, use_memo, use_ref, use_state)
from pyxpo.element import flatten
from pyxpo.ops import Create, Insert, Update, from_json, to_json
from pyxpo.renderers.mock import MockRenderer


def mount(root, **props):
    ch = LocalChannel()
    r = MockRenderer(ch)
    app = create_app(root, ch, **props)
    return app, r


def test_flatten_and_text_children():
    els = flatten([None, [Text("a"), "b"], False, 3])
    assert [e.props["text"] for e in els] == ["a", "b", "3"]
    assert Text("Count: ", 5).props["text"] == "Count: 5"


def test_ops_json_roundtrip():
    ops = [Create(2, "Text", {"text": "x"}), Update(2, {"text": "y"}, ["style"]), Insert(1, 2, 0)]
    assert from_json(to_json(ops)) == ops


def test_counter_end_to_end():
    @component
    def Counter(start=0):
        n, set_n = use_state(start)
        return View(Text("Count: ", n), Button(title="Add", on_press=lambda: set_n(lambda c: c + 1)))

    app, r = mount(Counter, start=5)
    assert r.texts() == ["Count: 5"]
    r.press(r.find_text("Add"))
    r.press(r.find_text("Add"))
    assert r.texts() == ["Count: 7"]


def test_hooks_outside_render_and_order_errors():
    with pytest.raises(HookError):
        use_state(0)

    flag = {"on": True}

    @component
    def Bad():
        if flag["on"]:
            use_state(0)
        use_ref()
        return None

    app, r = mount(Bad)
    flag["on"] = False
    with pytest.raises(HookError):
        app.rec.update(app.rec.root.children[0])


def test_effects_deps_and_cleanup():
    log = []

    @component
    def C():
        n, set_n = use_state(0)
        use_effect(lambda: log.append("always"))
        use_effect(lambda: (log.append("once"), lambda: log.append("once-cleanup"))[1], [])
        use_effect(lambda: (log.append("n=%d" % n), lambda: log.append("clean n=%d" % n))[1], [n])
        return Button(title="go", on_press=lambda: set_n(n + 1))

    @component
    def Root():
        show, set_show = use_state(True)
        return View(C() if show else None, Button(title="hide", on_press=lambda: set_show(False)))

    app, r = mount(Root)
    assert log == ["always", "once", "n=0"]
    del log[:]
    r.press(r.find_text("go"))
    assert log == ["clean n=0", "always", "n=1"]
    del log[:]
    r.press(r.find_text("hide"))
    assert sorted(log) == ["clean n=1", "once-cleanup"]
    assert r.find_text("go") is None


def test_memo_callback_ref_stable():
    seen = []

    @component
    def C():
        n, set_n = use_state(0)
        ref = use_ref([])
        cb = use_callback(lambda: None, [])
        m = use_memo(lambda: object(), [])
        seen.append((ref, cb, m))
        return Button(title="x", on_press=lambda: set_n(n + 1))

    app, r = mount(C)
    r.press(r.find_text("x"))
    assert len(seen) == 2 and all(a is b for a, b in zip(seen[0], seen[1]))


def test_same_state_does_not_rerender():
    renders = []

    @component
    def C():
        n, set_n = use_state(1)
        renders.append(n)
        return Button(title="x", on_press=lambda: set_n(1))

    app, r = mount(C)
    r.press(r.find_text("x"))
    assert renders == [1]


def test_context():
    Theme = create_context("light")

    @component
    def Leaf():
        return Text(use_context(Theme))

    app, r = mount(lambda: View(Leaf(), Theme.Provider(Leaf(), value="dark")))
    assert r.texts() == ["light", "dark"]


def test_prop_diff_emits_minimal_update():
    @component
    def C():
        n, set_n = use_state(0)
        return View(Text("same"), Text("n", n, style={"a": 1} if n == 0 else {}), Button(title="b", on_press=lambda: set_n(1)))

    app, r = mount(C)
    sent = []
    orig = r.apply_json
    r.channel.set_native_handler(lambda s: (sent.append(s), orig(s)))
    r.press(r.find_text("b"))
    assert len(sent) == 1
    ops = from_json(sent[0])
    assert [type(o).__name__ for o in ops] == ["Update"]
    assert ops[0].props == {"text": "n1", "style": {}} and ops[0].removed == []


def test_keyed_reorder_add_remove():
    @component
    def List():
        items, set_items = use_state(["a", "b", "c"])
        return View(*[Text(i, key=i) for i in items],
                    Button(title="ab", on_press=lambda: set_items(["c", "a", "x", "b"])),
                    Button(title="rm", on_press=lambda: set_items(["b"])),
                    Button(title="rev", on_press=lambda: set_items(list(reversed(items)))))

    app, r = mount(List)
    ids = {t.props["text"]: t.id for t in r.find_all("Text")}
    r.press(r.find_text("ab"))
    assert r.texts() == ["c", "a", "x", "b"]
    assert r.find_text("a").id == ids["a"] and r.find_text("c").id == ids["c"]  # kept, not recreated
    r.press(r.find_text("rm"))
    assert r.texts() == ["b"]
    assert sorted(r.attached_ids()) == sorted(r.nodes)  # nothing leaked, deleted nodes gone


def test_fragments_and_conditional_siblings():
    @component
    def Frag(on):
        return [Text("f1"), Text("f2")] if on else None

    @component
    def Root():
        on, set_on = use_state(False)
        return View(Text("head"), Frag(on=on), Text("tail"), Button(title="t", on_press=lambda: set_on(not on)))

    app, r = mount(Root)
    assert r.texts() == ["head", "tail"]
    r.press(r.find_text("t"))
    assert r.texts() == ["head", "f1", "f2", "tail"]
    r.press(r.find_text("t"))
    assert r.texts() == ["head", "tail"]
    assert sorted(r.attached_ids()) == sorted(r.nodes)


def test_handler_with_value_and_zero_args():
    got = []

    @component
    def C():
        return View(Text("t"), Button(title="go", on_press=lambda: got.append("p")),
                    View(key=None, on_change_text=got.append))

    app, r = mount(C)
    r.press(r.find_text("go"))
    r.type_text([n for n in r.find_all("View") if n.props.get("on_change_text")][0], "hi")
    assert got == ["p", "hi"]


def test_error_overlay_colors_are_native_ints_and_clear():
    app, r = mount(lambda: View(Text("x")))
    app.show_error("boom")
    label = [n for n in r.find_all("Text") if n.props.get("text") == "boom"][0]
    box = [n for n in r.find_all("View") if isinstance(n.props.get("style", {}).get("background_color"), int)][0]
    assert isinstance(label.props["style"]["color"], int) and isinstance(box.props["style"]["background_color"], int)
    app.clear_error()
    assert r.texts() == ["x"]


def test_app_reload_resets_state_and_runs_dev_hook():
    @component
    def C():
        n, set_n = use_state(0)
        return View(Text("n", n), Button(title="add", on_press=lambda: set_n(n + 1)))

    app, r = mount(C)
    r.press(r.find_text("add"))
    assert r.texts() == ["n1"]
    called = []
    app.dev_reload = lambda: (called.append(1), app.reload())[1]
    app._handle_event('{"id": 0, "event": "dev_reload"}')
    assert called and r.texts() == ["n0"]


def test_native_remount_mounts_again_on_new_renderer():
    from pyxpo import Animated
    from pyxpo.animated.nodes import Value
    shared = Value(0.5)  # lives outside the tree: must register again on the new native side

    @component
    def C():
        n, set_n = use_state(0)
        return View(Text("n", n), Button(title="add", on_press=lambda: set_n(n + 1)),
                    Animated.View(style={"opacity": shared}))

    app, r = mount(C)
    r.press(r.find_text("add"))
    assert r.texts() == ["n1"] and shared.id in r.driver.nodes
    r2 = MockRenderer(app.channel)  # Android made a new activity: empty native tree, same Python
    app._handle_event('{"id": 0, "event": "remount", "payload": {"n": 7, "env": {"color_scheme": "dark"}}}')
    assert r2.marks == [7] and r2.texts() == ["n0"] and shared.id in r2.driver.nodes
    assert app.env.get()["color_scheme"] == "dark"
    r2.press(r2.find_text("add"))
    assert r2.texts() == ["n1"]


def test_invalid_child_error_says_to_use_a_keyword():
    """A data object passed positionally becomes a child; the error tells how to pass it instead."""
    from pyxpo import View, component

    class Board:
        pass

    @component
    def Panel(board=None):
        return View()

    with pytest.raises(TypeError, match=r"invalid child of type Board: .*keyword props"):
        Panel(Board())
