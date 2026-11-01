from __future__ import annotations

from pyxpo import Animated, Easing, Text, View, component, use_animated_value
from pyxpo.animated import runtime
from pyxpo.animated.nodes import Value

from .test_core import mount


def _find(r, type="View"):
    return r.find_all(type)[0]


def test_timing_native_no_per_frame_ops():
    holder = {}

    @component
    def App():
        v = use_animated_value(0)
        holder["v"] = v
        return View(style={"opacity": v, "width": 10})

    app, r = mount(App)
    v = holder["v"]
    n = _find(r)
    base = r.batches
    Animated.timing(v, 1, duration=200, easing=Easing.linear).start()
    after_start = r.batches
    r.advance(116)     # start time = first frame after the op (16 ms)
    assert abs(r.resolved(n, "opacity") - 0.5) < 0.05
    r.advance(200)
    assert r.resolved(n, "opacity") == 1
    assert r.batches == after_start          # no ops during frames
    assert after_start > base


def test_end_callback_and_value():
    holder = {}

    @component
    def App():
        holder["v"] = use_animated_value(0)
        return View(style={"opacity": holder["v"]})

    app, r = mount(App)
    done = []
    Animated.timing(holder["v"], 1, duration=100).start(lambda res: done.append(res["finished"]))
    r.advance(300)
    assert done == [True]
    assert holder["v"].get_value() == 1


def test_interpolate_and_interrupt():
    holder = {}

    @component
    def App():
        v = use_animated_value(0)
        holder["v"] = v
        return View(style={"translate_x": v.interpolate([0, 1], [0, 100])})

    app, r = mount(App)
    n = _find(r)
    res = []
    Animated.timing(holder["v"], 1, duration=100, easing=Easing.linear).start(lambda x: res.append(x["finished"]))
    r.advance(50)
    Animated.timing(holder["v"], 0, duration=100, easing=Easing.linear).start()
    r.advance(10)
    assert res == [False]
    r.advance(500)
    assert r.resolved(n, "translate_x") == 0


def test_unmount_deletes_node():
    holder = {}

    @component
    def Child():
        holder["v"] = use_animated_value(0)
        return View(style={"opacity": holder["v"]})

    @component
    def App(show=True):
        return View(Child() if show else None)

    app, r = mount(App)
    assert holder["v"].id in r.driver.nodes
    app.set_root(App, show=False)
    app.hot_refresh()
    assert holder["v"].id not in r.driver.nodes


def test_python_fallback_ticks():
    holder = {}

    @component
    def App():
        holder["v"] = use_animated_value(0)
        return View(style={"opacity": holder["v"]})

    app, r = mount(App)
    t = [0.0]
    runtime._clock = lambda: t[0]
    try:
        done = []
        Animated.timing(holder["v"], 1, duration=100, easing=lambda x: x, use_native_driver=False).start(
            lambda x: done.append(x["finished"]))
        runtime.py_tick()          # first tick sets the start time
        t[0] = 50
        runtime.py_tick()
        assert abs(holder["v"].get_value() - 0.5) < 0.01
        t[0] = 200
        runtime.py_tick()
        assert done == [True] and holder["v"].get_value() == 1
    finally:
        runtime._clock = None


def test_golden_matches_engine():
    import json
    import os
    from pyxpo.animated import easing, engine
    g = json.load(open(os.path.join(os.path.dirname(__file__), "data", "anim_golden.json")))
    for c in g["easing"]:
        for t, v in zip(c["t"], c["v"]):
            assert abs(easing.fn(c["spec"])(t) - v) < 1e-9
    for c in g["spring"]:
        for t, v in zip(c["dt"], c["v"]):
            x, vel = engine.spring_at(t / 1000.0, 0.0, c["v0"], c["k"], c["c"], c["m"])
            assert abs(x - v[0]) < 1e-9 and abs(vel - v[1]) < 1e-9


def test_spring_settles_and_sequence_parallel():
    holder = {}

    @component
    def App():
        holder["a"], holder["b"] = use_animated_value(0), use_animated_value(0)
        return View(style={"opacity": holder["a"], "scale": holder["b"]})

    app, r = mount(App)
    a, b = holder["a"], holder["b"]
    done = []
    Animated.sequence([
        Animated.spring(a, 1),
        Animated.parallel([Animated.timing(b, 2, duration=100), Animated.timing(a, 0, duration=100)]),
    ]).start(lambda x: done.append(x["finished"]))
    r.advance(10000)
    assert done == [True]
    assert a.get_value() == 0 and b.get_value() == 2


def test_stop_and_set_value():
    holder = {}

    @component
    def App():
        holder["v"] = use_animated_value(0)
        return View(style={"opacity": holder["v"]})

    app, r = mount(App)
    v = holder["v"]
    res = []
    anim = Animated.timing(v, 1, duration=1000, easing=Easing.linear)
    anim.start(lambda x: res.append(x["finished"]))
    r.advance(200)
    anim.stop()
    r.advance(100)
    assert res == [False]
    v.set_value(0.25)
    assert r.resolved(_find(r), "opacity") == 0.25
    assert v.get_value() == 0.25


def test_loop_and_stagger():
    holder = {}

    @component
    def App():
        holder["a"], holder["b"] = use_animated_value(0), use_animated_value(0)
        return View(style={"opacity": holder["a"], "scale": holder["b"]})

    app, r = mount(App)
    a, b = holder["a"], holder["b"]
    Animated.loop(Animated.timing(a, 1, duration=100, easing=Easing.linear)).start()
    r.advance(1000)
    assert r.driver.anims          # still running
    Animated.stagger(50, [Animated.timing(b, 1, duration=50), Animated.timing(b, 2, duration=50)])


def test_value_xy_translate_and_timing():
    holder = {}

    @component
    def App():
        if "xy" not in holder:
            holder["xy"] = Animated.ValueXY({"x": 0, "y": 0})
        return View(style={"transform": holder["xy"].getTranslateTransform(), "width": 10})

    app, r = mount(App)
    xy = holder["xy"]
    Animated.timing(xy, {"x": 100, "y": 50}, duration=100, easing=Easing.linear).start()
    r.advance(300)
    n = _find(r)
    assert r.resolved(n, "translate_x") == 100 and r.resolved(n, "translate_y") == 50
    xy.setValue({"x": 5, "y": 6})
    assert xy.getValue() == {"x": 5.0, "y": 6.0}
