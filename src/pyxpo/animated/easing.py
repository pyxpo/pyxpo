"""Easing curves. `Easing.*` build plain-dict specs (serialisable to the native driver); `fn(spec)` turns one into a callable.

The same formulas are ported to Kotlin and Swift. tests/data/anim_golden.json pins the shared numbers.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, Optional

Spec = Dict[str, Any]


def _bezier(x1: float, y1: float, x2: float, y2: float) -> Callable[[float], float]:
    def coord(a: float, b: float, t: float) -> float:
        u = 1 - t
        return 3 * u * u * t * a + 3 * u * t * t * b + t * t * t

    def f(x: float) -> float:
        if x <= 0:
            return 0.0
        if x >= 1:
            return 1.0
        lo, hi, t = 0.0, 1.0, x
        for _ in range(40):  # bisection: monotonic in t for x1, x2 in [0, 1]
            cx = coord(x1, x2, t)
            if abs(cx - x) < 1e-7:
                break
            if cx < x:
                lo = t
            else:
                hi = t
            t = (lo + hi) / 2
        return coord(y1, y2, t)

    return f


def _bounce(t: float) -> float:
    if t < 1 / 2.75:
        return 7.5625 * t * t
    if t < 2 / 2.75:
        t -= 1.5 / 2.75
        return 7.5625 * t * t + 0.75
    if t < 2.5 / 2.75:
        t -= 2.25 / 2.75
        return 7.5625 * t * t + 0.9375
    t -= 2.625 / 2.75
    return 7.5625 * t * t + 0.984375


def fn(spec: Any) -> Callable[[float], float]:
    if spec is None:
        return fn(Easing.in_out(Easing.quad))  # RN default for timing
    if callable(spec):
        return spec
    e = spec["e"]
    if e == "linear":
        return lambda t: t
    if e == "ease":
        return _bezier(0.42, 0, 1, 1)
    if e == "quad":
        return lambda t: t * t
    if e == "cubic":
        return lambda t: t * t * t
    if e == "poly":
        n = spec.get("n", 4)
        return lambda t: t ** n
    if e == "sin":
        return lambda t: 1 - math.cos(t * math.pi / 2)
    if e == "circle":
        return lambda t: 1 - math.sqrt(max(0.0, 1 - t * t))
    if e == "exp":
        return lambda t: 2 ** (10 * (t - 1))
    if e == "elastic":
        p = spec.get("b", 1) * math.pi
        return lambda t: 1 - math.cos(t * math.pi / 2) ** 3 * math.cos(t * p)
    if e == "back":
        s = spec.get("s", 1.70158)
        return lambda t: t * t * ((s + 1) * t - s)
    if e == "bounce":
        return _bounce
    if e == "bezier":
        return _bezier(*spec["p"])
    if e == "in":
        return fn(spec["f"])
    if e == "out":
        f = fn(spec["f"])
        return lambda t: 1 - f(1 - t)
    if e == "in_out":
        f = fn(spec["f"])
        return lambda t: f(2 * t) / 2 if t < 0.5 else 1 - f(2 * (1 - t)) / 2
    raise ValueError("unknown easing %r" % (e,))


def is_native(spec: Any) -> bool:
    return spec is None or isinstance(spec, dict)


class Easing:
    linear: Spec = {"e": "linear"}
    ease: Spec = {"e": "ease"}
    quad: Spec = {"e": "quad"}
    cubic: Spec = {"e": "cubic"}
    sin: Spec = {"e": "sin"}
    circle: Spec = {"e": "circle"}
    exp: Spec = {"e": "exp"}
    bounce: Spec = {"e": "bounce"}

    @staticmethod
    def poly(n: float) -> Spec:
        return {"e": "poly", "n": n}

    @staticmethod
    def back(s: float = 1.70158) -> Spec:
        return {"e": "back", "s": s}

    @staticmethod
    def elastic(bounciness: float = 1) -> Spec:
        return {"e": "elastic", "b": bounciness}

    @staticmethod
    def bezier(x1: float, y1: float, x2: float, y2: float) -> Spec:
        return {"e": "bezier", "p": [x1, y1, x2, y2]}

    @staticmethod
    def in_(f: Any) -> Spec:
        return {"e": "in", "f": f}

    @staticmethod
    def out(f: Any) -> Spec:
        return {"e": "out", "f": f}

    @staticmethod
    def in_out(f: Any) -> Optional[Spec]:
        return {"e": "in_out", "f": f}
