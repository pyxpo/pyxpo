from __future__ import annotations

import pytest

from pyxpo import App, Button, ErrorBoundary, LocalChannel, Text, View, component, use_effect, use_state
from pyxpo.renderers.mock import MockRenderer


def mount(root, **props):
    ch = LocalChannel()
    r = MockRenderer(ch)
    app = App(root, ch, None, **props)
    errors = []
    app.on_error = errors.append
    app.start()
    check(app, r)
    return app, r, errors


def _hosts(f):
    for c in f.children:
        assert not c.unmounted
        if c.kind == "host":
            yield c
        yield from _hosts(c)


def check(app, r):
    """Native tree == fiber tree: no leaked creates, no missing inserts, no stale handlers."""
    hosts = list(_hosts(app.rec.root))
    ids = {h.id for h in hosts}
    assert set(r.nodes) == {1} | ids
    for h in [app.rec.root] + hosts:
        assert [c.id for c in r.nodes[h.id].children] == h.native
    assert {k[0] for k in app.rec.handlers} <= ids
    assert app.rec.ops == [] and app.rec._deletes == []


def Fallback(error, reset):
    return View(Text("oops: %s" % error), Button("retry", on_press=reset))


def test_mount_error_shows_fallback():
    caught = []

    @component
    def Bad():
        raise ValueError("bad")

    @component
    def Root():
        return View(Text("top"), ErrorBoundary(Text("inner"), View(Text("deep"), Bad()), fallback=Fallback,
                                               onError=caught.append), Text("bottom"))

    app, r, errors = mount(Root)
    assert r.texts() == ["top", "oops: bad", "bottom"]
    assert [str(e) for e in caught] == ["bad"] and errors == []


def test_fallback_element_and_none():
    @component
    def Bad():
        raise ValueError("x")

    @component
    def Root():
        return View(ErrorBoundary(Bad(), fallback=Text("static")), ErrorBoundary(Bad()), Text("end"))

    app, r, _ = mount(Root)
    assert r.texts() == ["static", "end"]


def test_update_error_in_deep_child_shows_fallback_and_siblings_untouched():
    effects = []
    box = {}

    @component
    def Deep():
        n, set_n = use_state(0)
        box["set"] = set_n
        use_effect(lambda: (effects.append("run %d" % n), lambda: effects.append("clean %d" % n))[1], [n])
        if n == 2:
            raise RuntimeError("deep %d" % n)
        return View(Text("deep %d" % n), *[Text("extra %d" % i, key=i) for i in range(n)])

    @component
    def Root():
        s, set_s = use_state(0)
        box["root"] = set_s
        return View(Text("sib %d" % s), ErrorBoundary(View(Text("a"), View(Deep())), fallback=Fallback),
                    Text("after"))

    app, r, errors = mount(Root)
    box["set"](1)
    check(app, r)
    assert r.texts() == ["sib 0", "a", "deep 1", "extra 0", "after"]
    sib = r.find_text("sib 0")
    box["set"](2)
    check(app, r)
    assert r.texts() == ["sib 0", "oops: deep 2", "after"]
    assert r.find_text("sib 0") is sib  # the sibling native node survived
    assert effects == ["run 0", "clean 0", "run 1", "clean 1"]  # n=2 effect never ran; unmount cleaned n=1
    box["root"](1)  # parent re-render keeps the fallback
    check(app, r)
    assert r.texts() == ["sib 1", "oops: deep 2", "after"]
    assert errors == []


def test_update_error_in_sibling_during_parent_rerender():
    @component
    def Maybe(n=0):
        if n == 1:
            raise ValueError("n1")
        return Text("m%d" % n)

    @component
    def Root():
        n, set_n = use_state(0)
        return View(ErrorBoundary(Text("x%d" % n, key="x"), View(Text("y%d" % n), Maybe(n=n)), Text("z%d" % n),
                                  fallback=Fallback),
                    Button("go", on_press=lambda: set_n(n + 1)))

    app, r, _ = mount(Root)
    r.press(r.find_text("go"))
    check(app, r)
    assert r.texts() == ["oops: n1"]


def test_no_leaked_handlers_or_creates():
    @component
    def Row(i=0, fail=False):
        if fail and i == 7:
            raise ValueError("row")
        return Button("b%d" % i, on_press=lambda: None)

    @component
    def List():
        fail, set_fail = use_state(False)
        return View(Button("fail", on_press=lambda: set_fail(True)),
                    *[Row(i=i, fail=fail, key=i) for i in range(5)],
                    *([Row(i=i, fail=fail, key=i) for i in range(5, 10)] if fail else []))

    @component
    def Root():
        return ErrorBoundary(List(), fallback=Fallback)

    app, r, _ = mount(Root)
    n_before = app.rec._next_id
    r.press(r.find_text("fail"))
    check(app, r)
    assert r.texts() == ["oops: row"]
    assert all(k[0] < n_before or r.nodes.get(k[0]) is not None for k in app.rec.handlers)


def test_reset_rerenders_children():
    state = {"fail": True}

    @component
    def Flaky():
        if state["fail"]:
            raise ValueError("flaky")
        return Text("ok")

    @component
    def Root():
        return View(ErrorBoundary(Flaky(), fallback=Fallback), Text("end"))

    app, r, _ = mount(Root)
    assert r.texts() == ["oops: flaky", "end"]
    state["fail"] = False
    r.press(r.find_text("retry"))
    check(app, r)
    assert r.texts() == ["ok", "end"]
    state["fail"] = True
    app.rec.update(app.rec.root.children[0])  # re-render Root: Flaky fails again -> fallback
    app._send(app.rec.take_ops())
    check(app, r)
    assert r.texts() == ["oops: flaky", "end"]


def test_nested_boundaries_fallback_error_goes_outer():
    @component
    def Bad():
        raise ValueError("inner")

    def bad_fallback(error, reset):
        raise KeyError("fallback")

    outer = []

    @component
    def Root():
        return View(ErrorBoundary(Text("o1"), ErrorBoundary(Bad(), fallback=bad_fallback), fallback=Fallback,
                                  on_error=outer.append), Text("end"))

    app, r, _ = mount(Root)
    assert r.texts()[1] == "end" and r.texts()[0].startswith("oops: ")
    assert [type(e) for e in outer] == [KeyError]


def test_nested_boundaries_inner_catches_on_update():
    box = {}

    @component
    def Deep():
        n, set_n = use_state(0)
        box["set"] = set_n
        if n:
            raise ValueError("d")
        return Text("deep")

    inner, outer = [], []

    @component
    def Root():
        return ErrorBoundary(View(Text("o"), ErrorBoundary(View(Deep()), fallback=Text("inner fb"),
                                                           on_error=inner.append)),
                             fallback=Text("outer fb"), on_error=outer.append)

    app, r, _ = mount(Root)
    box["set"](1)
    check(app, r)
    assert r.texts() == ["o", "inner fb"] and len(inner) == 1 and outer == []


def test_no_boundary_behavior_unchanged():
    @component
    def Bad():
        raise ValueError("unhandled")

    ch = LocalChannel()
    MockRenderer(ch)
    with pytest.raises(ValueError, match="unhandled"):
        App(View(Bad()), ch, None).start()

    box = {}

    @component
    def Later():
        n, set_n = use_state(0)
        box["set"] = set_n
        if n:
            raise ValueError("later")
        return Text("fine")

    app, r, _ = mount(View(Later()))
    with pytest.raises(ValueError, match="later"):
        box["set"](1)


def test_partial_update_with_removals_and_mounts_rolls_back():
    @component
    def Maybe(n=0):
        if n == 1:
            raise ValueError("n1")
        return Text("m%d" % n)

    @component
    def Root():
        n, set_n = use_state(0)
        rows = [Text("r%d" % i, key=i) for i in ([0, 1, 2] if n == 0 else [2, 5, 6])]
        return View(ErrorBoundary(View(*rows), View(View(Text("new")) if n else None, Maybe(n=n)),
                                  fallback=Fallback),
                    Button("go", on_press=lambda: set_n(n + 1)))

    app, r, _ = mount(Root)
    r.press(r.find_text("go"))
    check(app, r)
    assert r.texts() == ["oops: n1"]
    r.press(r.find_text("retry"))  # n is still 1: fails again, still consistent
    check(app, r)
    r.press(r.find_text("go"))
    r.press(r.find_text("retry"))
    check(app, r)
    assert r.texts() == ["r2", "r5", "r6", "new", "m2"]


def test_rollback_releases_refs_animated_nodes_and_setters_of_unattached_fibers():
    from pyxpo import ScrollRef, ScrollView, use_animated_value

    sref = ScrollRef()
    setters = []

    @component
    def Animated1():
        v = use_animated_value(1.0)
        _, set_x = use_state(0)
        setters.append(set_x)
        return View(style={"opacity": v})

    @component
    def Bad():
        raise ValueError("bad")

    @component
    def Root():
        # Animated1 and the ScrollView mount before Bad fails: the partial child list is never attached
        return View(ErrorBoundary(View(Animated1(), ScrollView(Text("s"), ref=sref), Bad()), fallback=Fallback))

    app, r, errors = mount(Root)
    assert r.texts() == ["oops: bad"] and errors == []
    assert sref.id is None  # not bound to a view that native never got
    assert r.driver.nodes == {}  # the Value's node was never created natively (its freeing effect never runs)
    dirty = list(app.dirty)
    setters[0](5)  # the rolled-back fiber is unmounted: no re-render scheduled
    assert app.dirty == dirty
    check(app, r)


def test_rolled_back_animated_value_registers_again_when_reused():
    from pyxpo.animated import Value

    shared = Value(0.5)  # outlives the rolled-back render

    @component
    def Root():
        fail, set_fail = use_state(True)

        @component
        def Maybe():
            if fail:
                raise ValueError("x")
            return Text("ok")

        return View(ErrorBoundary(View(View(style={"opacity": shared}), Maybe()), fallback=Fallback),
                    View(style={"opacity": shared}) if not fail else None,
                    Button("fix", on_press=lambda: set_fail(False)))

    app, r, _ = mount(Root)
    assert shared.id not in r.driver.nodes and shared._token is None
    r.press(r.find_text("fix"))
    assert shared.id in r.driver.nodes  # wired again by the sibling: registered again
