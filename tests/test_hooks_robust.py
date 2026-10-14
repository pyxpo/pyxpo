"""Hook and runtime robustness (effect order, error isolation, deps checks) and the newer React hooks."""
from __future__ import annotations

import asyncio
import math
import warnings

import pytest

import pyxpo
from pyxpo import (App, Button, HookError, LocalChannel, Text, View, component, create_app, use_effect, use_id,
                   use_imperative_handle, use_memo, use_reducer, use_ref, use_state, use_sync_external_store,
                   use_transition, use_deferred_value, use_debug_value, use_layout_effect)
from pyxpo.renderers.mock import MockRenderer


def mount(root, **props):
    ch = LocalChannel()
    r = MockRenderer(ch)
    app = App(root, ch, None, **props)
    errors = []
    app.on_error = errors.append
    app.start()
    return app, r, errors


def test_effect_runs_after_commit():
    seen = []

    @component
    def C():
        use_effect(lambda: seen.append(r.texts()), [])
        return Text("hello")

    ch = LocalChannel()
    r = MockRenderer(ch)
    create_app(C, ch)
    assert seen == [["hello"]]


def test_cleanup_before_rerun_on_dep_change_and_prop_change_only():
    log = []

    @component
    def Child(v=0, other=0):
        use_effect(lambda: (log.append("run %d" % v), lambda: log.append("clean %d" % v))[1], [v])
        return Text(str(v), str(other))

    @component
    def Root():
        s, set_s = use_state((0, 0))
        return View(Child(v=s[0], other=s[1]), Button(title="v", on_press=lambda: set_s((s[0] + 1, s[1]))),
                    Button(title="o", on_press=lambda: set_s((s[0], s[1] + 1))))

    app, r, errors = mount(Root)
    assert log == ["run 0"]
    r.press(r.find_text("o"))
    assert log == ["run 0"]  # unrelated prop changed: effect not re-run
    r.press(r.find_text("v"))
    assert log == ["run 0", "clean 0", "run 1"]
    assert errors == []


def test_cleanup_on_unmount_and_on_key_change():
    log = []

    @component
    def Child(k=0):
        use_effect(lambda: (log.append("run %d" % k), lambda: log.append("clean %d" % k))[1], [])
        return Text(str(k))

    @component
    def Root():
        k, set_k = use_state(0)
        return View(Child(k=k, key=k) if k < 2 else None, Button(title="next", on_press=lambda: set_k(k + 1)))

    app, r, _ = mount(Root)
    r.press(r.find_text("next"))
    assert log == ["run 0", "clean 0", "run 1"]
    r.press(r.find_text("next"))
    assert log == ["run 0", "clean 0", "run 1", "clean 1"]


def test_empty_deps_runs_once():
    runs = []

    @component
    def C():
        n, set_n = use_state(0)
        use_effect(lambda: runs.append(1), [])
        use_layout_effect(lambda: runs.append(2), ())
        return Button(title="go", on_press=lambda: set_n(n + 1))

    app, r, _ = mount(C)
    for _ in range(3):
        r.press(r.find_text("go"))
    assert runs == [1, 2]


def test_raising_effect_does_not_skip_others():
    log = []

    def boom():
        raise ValueError("effect")

    def boom_cleanup():
        def c():
            raise KeyError("cleanup")
        return c

    @component
    def C():
        n, set_n = use_state(0)
        use_effect(boom_cleanup)
        use_effect(boom)
        use_effect(lambda: log.append(n))
        return Button(title="go", on_press=lambda: set_n(n + 1))

    app, r, errors = mount(C)
    assert log == [0] and [type(e) for e in errors] == [ValueError]
    r.press(r.find_text("go"))
    assert log == [0, 1]
    assert [type(e) for e in errors] == [ValueError, KeyError, ValueError]
    r.press(r.find_text("go"))  # runtime still alive
    assert log == [0, 1, 2]


def test_effect_error_without_app_is_raised_after_all_effects():
    from pyxpo.reconciler import Reconciler
    log = []

    @component
    def C():
        use_effect(lambda: 1 / 0)
        use_effect(lambda: log.append("ran"))
        return None

    rec = Reconciler()
    rec.render(C())
    with pytest.raises(ZeroDivisionError):
        rec.run_effects()
    assert log == ["ran"]


def test_raising_cleanup_on_unmount_keeps_tree_consistent():
    def bad():
        def c():
            raise RuntimeError("cleanup")
        return c

    @component
    def Child():
        use_effect(bad, [])
        return View(Text("child"))

    @component
    def Root():
        show, set_show = use_state(True)
        return View(Child() if show else None, Child() if show else None, Text("stay"),
                    Button(title="hide", on_press=lambda: set_show(False)))

    app, r, errors = mount(Root)
    r.press(r.find_text("hide"))
    assert [str(e) for e in errors] == ["cleanup", "cleanup"]
    assert r.texts() == ["stay"] and r.find_text("hide") is not None
    assert set(r.nodes) == {1} | {f.id for f in _hosts(app.rec.root)}


def _hosts(f):
    for c in f.children:
        if c.kind == "host":
            yield c
        yield from _hosts(c)


def test_first_render_exception_then_success_hooks_aligned():
    flag = {"fail": True}

    @component
    def C():
        a, _ = use_state("a")
        if flag["fail"]:
            raise ValueError("first")
        b = use_ref("b")
        return Text(a, b.current)

    ch = LocalChannel()
    MockRenderer(ch)
    app = App(C, ch, None)
    with pytest.raises(ValueError):
        app.start()
    fiber = app.rec.root.children[0] if app.rec.root.children else None
    assert fiber is None  # the failed mount left nothing behind
    # the same fiber object re-rendered after a failed first render
    from pyxpo.hooks import render_with_hooks
    from pyxpo.reconciler import Fiber
    f = Fiber("comp", C(), app.rec.root, app.rec)
    with pytest.raises(ValueError):
        render_with_hooks(f, C.fn, (), {})
    assert f.hooks == [] and not f.hooks_ready
    flag["fail"] = False
    render_with_hooks(f, C.fn, (), {})
    assert [k for k, _ in f.hooks] == ["state", "ref"]


def test_hook_order_violation_errors():
    mode = {"m": "base"}

    @component
    def C():
        if mode["m"] == "swap":
            use_ref()
            use_state(0)
        else:
            use_state(0)
            if mode["m"] != "fewer":
                use_ref()
            if mode["m"] == "more":
                use_memo(lambda: 1, [])
        return None

    for m in ("more", "fewer", "swap"):
        app, r, _ = mount(C)
        mode["m"] = m
        with pytest.raises(HookError):
            app.rec.update(app.rec.root.children[0])
        mode["m"] = "base"


def test_bad_deps_type_errors():
    @component
    def C():
        use_effect(lambda: None, 5)
        return None

    @component
    def G():
        use_memo(lambda: 1, (x for x in [1]))
        return None

    for comp in (C, G):
        with pytest.raises(HookError, match="deps must be a list"):
            create_app(comp, LocalChannel())


def test_async_effect_warns_and_runs():
    log = []

    @component
    def C():
        async def eff():
            await asyncio.sleep(0)
            log.append("async ran")
        use_effect(eff, [])
        return None

    async def main():
        loop = asyncio.get_running_loop()
        ch = LocalChannel()
        app = App(C, ch, loop)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            app.start()
        assert any("async effect" in str(x.message) for x in w)
        for _ in range(5):
            await asyncio.sleep(0)

    asyncio.run(main())
    assert log == ["async ran"]


def test_async_effect_error_goes_to_on_error():
    @component
    def C():
        async def eff():
            raise ValueError("async boom")
        use_effect(eff, [])
        return None

    errors = []

    async def main():
        app = App(C, LocalChannel(), asyncio.get_running_loop())
        app.on_error = errors.append
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            app.start()
        for _ in range(5):
            await asyncio.sleep(0)

    asyncio.run(main())
    assert [str(e) for e in errors] == ["async boom"]


def test_nan_deps_stable():
    runs = []
    nan = float("nan")

    @component
    def C():
        n, set_n = use_state(0)
        use_effect(lambda: runs.append(1), [float("nan"), math.inf])
        return Button(title="go", on_press=lambda: set_n(n + 1))

    app, r, _ = mount(C)
    r.press(r.find_text("go"))
    assert runs == [1]
    from pyxpo.hooks import _same
    assert _same(nan, float("nan")) and not _same(nan, 1.0) and not _same(1.0, 2.0)


def test_handler_exception_reported_runtime_alive():
    @component
    def C():
        n, set_n = use_state(0)

        def bad():
            raise RuntimeError("handler")
        return View(Text("n=%d" % n), Button(title="bad", on_press=bad), Button(title="ok", on_press=lambda: set_n(n + 1)))

    app, r, errors = mount(C)
    r.press(r.find_text("bad"))
    r.press(r.find_text("ok"))
    assert [str(e) for e in errors] == ["handler"]
    assert r.texts()[0] == "n=1"


def test_hot_reload_reruns_effect_with_cleanup():
    log = []

    @component
    def C():
        use_effect(lambda: (log.append("run"), lambda: log.append("clean"))[1], [])
        return Text("x")

    app, r, _ = mount(C)
    assert app.hot_refresh() is None
    assert log == ["run", "clean", "run"]
    app.rec._unmount(app.rec.root.children[0])
    app.rec._unmount(app.rec.root.children[0])  # idempotent: cleanup runs once
    assert log == ["run", "clean", "run", "clean"]


def test_child_effect_before_parent():
    log = []

    @component
    def Leaf(name=""):
        use_effect(lambda: (log.append("run " + name), lambda: log.append("clean " + name))[1])
        return Text(name)

    @component
    def Mid():
        use_effect(lambda: (log.append("run mid"), lambda: log.append("clean mid"))[1])
        return View(Leaf(name="a"), Leaf(name="b"))

    @component
    def Root():
        n, set_n = use_state(0)
        use_effect(lambda: (log.append("run root"), lambda: log.append("clean root"))[1])
        return View(Mid(), Button(title="go", on_press=lambda: set_n(n + 1)))

    app, r, _ = mount(Root)
    assert log == ["run a", "run b", "run mid", "run root"]
    del log[:]
    r.press(r.find_text("go"))
    assert log == ["clean a", "clean b", "clean mid", "clean root", "run a", "run b", "run mid", "run root"]


# -- new hooks ------------------------------------------------------------------
def test_use_reducer():
    renders = []

    def reducer(state, action):
        if action == "inc":
            return state + 1
        if action == "same":
            return state
        raise ValueError(action)

    @component
    def C():
        n, dispatch = use_reducer(reducer, 5, init=lambda a: a * 2)
        renders.append(dispatch)
        return View(Text("n=%d" % n), Button(title="inc", on_press=lambda: dispatch("inc")),
                    Button(title="same", on_press=lambda: dispatch("same")))

    app, r, _ = mount(C)
    assert r.texts()[0] == "n=10"
    r.press(r.find_text("inc"))
    assert r.texts()[0] == "n=11"
    r.press(r.find_text("same"))
    assert len(renders) == 2 and renders[0] is renders[1]


def test_use_id_stable_unique():
    ids = []

    @component
    def Item():
        ids.append(use_id())
        return None

    @component
    def Root():
        n, set_n = use_state(0)
        return View(Item(), Item(), Button(title="go", on_press=lambda: set_n(n + 1)))

    app, r, _ = mount(Root)
    r.press(r.find_text("go"))
    assert ids[0] == ids[2] and ids[1] == ids[3] and ids[0] != ids[1]
    assert ids[0].startswith(":p") and ids[0].endswith(":")


def test_imperative_handle_sets_and_clears():
    @component
    def Input(handle=None):
        use_imperative_handle(handle, lambda: {"focus": "ok"}, [])
        return Text("in")

    seen = []

    @component
    def Root():
        ref = use_ref()
        show, set_show = use_state(True)
        use_effect(lambda: seen.append(ref.current), [show])
        return View(Input(handle=ref) if show else None, Button(title="hide", on_press=lambda: set_show(False)))

    app, r, _ = mount(Root)
    assert seen == [{"focus": "ok"}]  # child handle is set before the parent effect runs
    r.press(r.find_text("hide"))
    assert seen == [{"focus": "ok"}, None]


def test_sync_external_store_tears_down():
    store = {"v": 1, "subs": []}

    def subscribe(cb):
        store["subs"].append(cb)
        return lambda: store["subs"].remove(cb)

    def get():
        return store["v"]

    def set_v(v):
        store["v"] = v
        for cb in list(store["subs"]):
            cb()

    @component
    def Reader():
        v = use_sync_external_store(subscribe, get)
        return Text("v=%d" % v)

    @component
    def Root():
        show, set_show = use_state(True)
        return View(Reader() if show else None, Button(title="hide", on_press=lambda: set_show(False)))

    app, r, _ = mount(Root)
    assert r.texts()[0] == "v=1" and len(store["subs"]) == 1
    set_v(2)
    assert r.texts()[0] == "v=2"
    r.press(r.find_text("hide"))
    assert store["subs"] == []


def test_transition_deferred_debug():
    out = {}

    @component
    def C():
        pending, start = use_transition()
        start(lambda: out.setdefault("ran", True))
        out["pending"] = pending
        out["deferred"] = use_deferred_value(7)
        use_debug_value("x")
        return None

    mount(C)
    assert out == {"ran": True, "pending": False, "deferred": 7}


CAMEL = {
    "useState": "use_state", "useEffect": "use_effect", "useLayoutEffect": "use_layout_effect", "useRef": "use_ref",
    "useMemo": "use_memo", "useCallback": "use_callback", "useContext": "use_context", "useReducer": "use_reducer",
    "useId": "use_id", "useImperativeHandle": "use_imperative_handle",
    "useSyncExternalStore": "use_sync_external_store", "useTransition": "use_transition",
    "useDeferredValue": "use_deferred_value", "useDebugValue": "use_debug_value", "useAsync": "use_async",
    "createContext": "create_context", "useWindowDimensions": "use_window_dimensions",
    "useColorScheme": "use_color_scheme", "useSafeAreaInsets": "use_safe_area_insets", "useAnimatedValue": "use_animated_value",
}


def test_camel_aliases_are_same_objects():
    for camel, snake in CAMEL.items():
        assert getattr(pyxpo, camel) is getattr(pyxpo, snake), camel
        assert camel in pyxpo.__all__ and snake in pyxpo.__all__


def test_all_exports_importable():
    for name in pyxpo.__all__:
        assert hasattr(pyxpo, name), name
    assert "ErrorBoundary" in pyxpo.__all__
