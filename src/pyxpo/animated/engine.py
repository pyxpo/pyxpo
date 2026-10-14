"""Reference animation engine: node graph, interpolation, leaf/composite animations and the Driver.

Native drivers (Kotlin, Swift) are ports of this module. The mock renderer and the Python-driven fallback use it directly.
Time is in ms from a monotonic frame clock. Values are floats, colour nodes are ARGB ints.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from . import easing as easing_mod


# -- interpolation -------------------------------------------------------------------------------
def _lerp_color(a: int, b: int, f: float) -> int:
    out = 0
    for shift in (24, 16, 8, 0):
        ca, cb = (a >> shift) & 255, (b >> shift) & 255
        out |= max(0, min(255, int(round(ca + (cb - ca) * f)))) << shift
    return out


def interpolate(x: float, inp: List[float], out: List[Any], left: str = "extend", right: str = "extend",
                ease: Optional[Callable[[float], float]] = None, color: bool = False) -> Any:
    n = len(inp)
    if x < inp[0]:
        if left == "clamp":
            return out[0]
        if left == "identity":
            return x
        i = 0
    elif x > inp[-1]:
        if right == "clamp":
            return out[-1]
        if right == "identity":
            return x
        i = n - 2
    else:
        i = 0
        while i < n - 2 and x > inp[i + 1]:
            i += 1
    a, b = inp[i], inp[i + 1]
    f = 0.0 if b == a else (x - a) / (b - a)
    if ease is not None:
        f = ease(f) if 0 <= f <= 1 else f
    if color:
        return _lerp_color(out[i], out[i + 1], max(0.0, min(1.0, f)))
    return out[i] + (out[i + 1] - out[i]) * f


# -- spring --------------------------------------------------------------------------------------
def spring_at(dt: float, x0: float, v0: float, k: float, c: float, m: float) -> Tuple[float, float]:
    """Displacement and velocity (per second) of a damped spring `dt` seconds after release from x0 with velocity v0."""
    w0 = math.sqrt(k / m)
    z = c / (2 * math.sqrt(k * m))
    if abs(z - 1) < 1e-9:
        e = math.exp(-w0 * dt)
        b = v0 + w0 * x0
        return e * (x0 + b * dt), e * (v0 - w0 * b * dt)
    if z < 1:
        wd = w0 * math.sqrt(1 - z * z)
        e = math.exp(-z * w0 * dt)
        b = (v0 + z * w0 * x0) / wd
        cs, sn = math.cos(wd * dt), math.sin(wd * dt)
        return e * (x0 * cs + b * sn), e * ((b * wd - z * w0 * x0) * cs - (x0 * wd + z * w0 * b) * sn)
    s = w0 * math.sqrt(z * z - 1)
    r1, r2 = -z * w0 + s, -z * w0 - s
    c2 = (v0 - r1 * x0) / (r2 - r1)
    c1 = x0 - c2
    e1, e2 = math.exp(r1 * dt), math.exp(r2 * dt)
    return c1 * e1 + c2 * e2, c1 * r1 * e1 + c2 * r2 * e2


# -- running animations --------------------------------------------------------------------------
class Ctx:
    """What leaf animations need from the driver: read/write node values and read velocity (units/second)."""

    def __init__(self, driver: "Driver") -> None:
        self.d = driver

    def get(self, n: int) -> float:
        return self.d.values.get(n, 0.0)

    def set(self, n: int, v: float, t: float) -> None:
        d = self.d
        prev = d.prev.get(n)
        if prev is not None and t > prev[0]:
            d.vel[n] = (v - prev[1]) / ((t - prev[0]) / 1000.0)
        d.prev[n] = (t, v)
        d.values[n] = v

    def vel(self, n: int) -> float:
        return self.d.vel.get(n, 0.0)


class _Timing:
    def __init__(self, s: Dict[str, Any], c: Ctx) -> None:
        self.s, self.c, self.t0 = s, c, None
        self.ease = easing_mod.fn(s.get("easing"))

    def update(self, t: float) -> bool:
        s, n = self.s, self.s["node"]
        if self.t0 is None:
            self.t0, self.a = t, self.c.get(n)
            self.c.d.prev[n] = (t, self.a)
        ms = s["ms"]
        p = 1.0 if ms <= 0 else min(1.0, (t - self.t0) / ms)
        self.c.set(n, float(s["to"]) if p >= 1 else self.a + (s["to"] - self.a) * self.ease(p), t)
        return p >= 1


class _Spring:
    def __init__(self, s: Dict[str, Any], c: Ctx) -> None:
        self.s, self.c, self.t0 = s, c, None

    def update(self, t: float) -> bool:
        s, n = self.s, self.s["node"]
        to = s["to"]
        if self.t0 is None:
            self.t0, a = t, self.c.get(n)
            self.x0 = a - to
            v0 = s.get("v0")
            self.v0 = self.c.vel(n) if v0 is None else v0
            self.c.d.prev[n] = (t, a)
        x, v = spring_at((t - self.t0) / 1000.0, self.x0, self.v0, s["k"], s["c"], s["m"])
        done = abs(x) <= s.get("rest_d", 0.001) and abs(v) <= s.get("rest_v", 0.001)
        if s.get("clamp") and t > self.t0 and self.x0 != 0 and x * self.x0 <= 0:
            done = True
        if self.x0 == 0 and self.v0 == 0:
            done = True
        self.c.set(n, to if done else to + x, t)
        if done:
            self.c.d.vel[n] = 0.0
        return done


class _Decay:
    def __init__(self, s: Dict[str, Any], c: Ctx) -> None:
        self.s, self.c, self.t0 = s, c, None

    def update(self, t: float) -> bool:
        s, n = self.s, self.s["node"]
        d = s.get("decel", 0.998)
        if self.t0 is None:
            self.t0, self.a = t, self.c.get(n)
            v0 = s.get("v0")
            self.v0 = self.c.vel(n) / 1000.0 if v0 is None else v0   # per ms
            self.c.d.prev[n] = (t, self.a)
        k = 1 - d
        dt = t - self.t0
        self.c.set(n, self.a + self.v0 / k * (1 - math.exp(-k * dt)), t)
        v = self.v0 * math.exp(-k * dt)
        done = abs(v) * 16.67 < 0.1
        if done:
            self.c.d.vel[n] = 0.0
        return done


class _Delay:
    def __init__(self, s: Dict[str, Any], c: Ctx) -> None:
        self.s, self.t0 = s, None

    def update(self, t: float) -> bool:
        if self.t0 is None:
            self.t0 = t
        return t - self.t0 >= self.s["ms"]


class _Seq:
    def __init__(self, s: Dict[str, Any], c: Ctx) -> None:
        self.items = [build(i, c) for i in s["items"]]
        self.i = 0

    def update(self, t: float) -> bool:
        while self.i < len(self.items):
            if not self.items[self.i].update(t):
                return False
            self.i += 1
        return True


class _Par:
    def __init__(self, s: Dict[str, Any], c: Ctx) -> None:
        self.items = [build(i, c) for i in s["items"]]
        self.done = [False] * len(self.items)

    def update(self, t: float) -> bool:
        for k, it in enumerate(self.items):
            if not self.done[k]:
                self.done[k] = it.update(t)
        return all(self.done)


class _Loop:
    def __init__(self, s: Dict[str, Any], c: Ctx) -> None:
        self.s, self.c = s, c
        self.n = s.get("n", -1)
        self.i = 0
        self.cur: Any = None
        self.snap: Optional[Dict[int, float]] = None

    def update(self, t: float) -> bool:
        for _ in range(2):  # at most one restart per tick, so a zero-length item cannot spin forever
            if self.cur is None:
                if self.n >= 0 and self.i >= self.n:
                    return True
                if self.snap is None:
                    self.snap = {n: self.c.get(n) for n in nodes_of(self.s["item"])}
                elif self.s.get("reset", True):
                    for n, v in self.snap.items():
                        self.c.set(n, v, t)
                self.cur = build(self.s["item"], self.c)
                self.i += 1
            if not self.cur.update(t):
                return False
            self.cur = None
        return self.n >= 0 and self.i >= self.n


_KINDS = {"timing": _Timing, "spring": _Spring, "decay": _Decay, "delay": _Delay, "seq": _Seq, "par": _Par, "loop": _Loop}


def build(spec: Dict[str, Any], ctx: Ctx) -> Any:
    return _KINDS[spec["t"]](spec, ctx)


def nodes_of(spec: Dict[str, Any]) -> Set[int]:
    t = spec["t"]
    if "node" in spec:
        return {spec["node"]}
    if t in ("seq", "par"):
        out: Set[int] = set()
        for i in spec["items"]:
            out |= nodes_of(i)
        return out
    if t == "loop":
        return nodes_of(spec["item"])
    return set()


# -- driver --------------------------------------------------------------------------------------
class Driver:
    """Holds animated nodes and running animations; `tick(now_ms)` advances them and returns events for Python."""

    def __init__(self) -> None:
        self.nodes: Dict[int, Dict[str, Any]] = {}
        self.values: Dict[int, float] = {}
        self.vel: Dict[int, float] = {}
        self.prev: Dict[int, Tuple[float, float]] = {}
        self.anims: Dict[int, Tuple[Any, Set[int]]] = {}
        self.listen: Set[int] = set()
        self._last: Dict[int, float] = {}
        self.touched: Set[int] = set()
        self.ctx = Ctx(self)

    # ops
    def anode(self, nid: int, node: Dict[str, Any]) -> None:
        self.nodes[nid] = node
        if node["t"] == "value":
            self.values[nid] = float(node.get("v", 0.0))
        elif node["t"] == "interp":
            node = dict(node)
            node["_ease"] = easing_mod.fn(node.get("easing")) if node.get("easing") is not None else None
            self.nodes[nid] = node

    def anode_del(self, nid: int) -> List[Dict[str, Any]]:
        ev = self._stop_touching({nid}, False)
        for d in (self.nodes, self.values, self.vel, self.prev, self._last):
            d.pop(nid, None)
        self.listen.discard(nid)
        return ev

    def alisten(self, nid: int, on: bool) -> None:
        (self.listen.add if on else self.listen.discard)(nid)
        if on:
            self._last[nid] = self.values.get(nid, 0.0)

    def animate(self, aid: int, spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        ns = nodes_of(spec)
        ev = self._stop_touching(ns, False)
        self.anims[aid] = (build(spec, self.ctx), ns)
        return ev

    def astop(self, aid: int) -> List[Dict[str, Any]]:
        a = self.anims.pop(aid, None)
        return [self._end(aid, False, a[1])] if a else []

    def aset(self, vals: Dict[Any, float]) -> List[Dict[str, Any]]:
        ids = {int(k) for k in vals}
        ev = self._stop_touching(ids, False)
        for k, v in vals.items():
            k = int(k)
            self.values[k] = float(v)
            self.vel[k] = 0.0
            self.prev.pop(k, None)
        ev += self._value_events(ids)
        return ev

    # evaluation
    def resolve(self, nid: int) -> Any:
        n = self.nodes.get(nid)
        if n is None:
            return 0.0
        t = n["t"]
        if t == "value":
            return self.values.get(nid, 0.0)
        if t == "interp":
            return interpolate(self.resolve(n["src"]), n["in"], n["out"], n["ex"][0], n["ex"][1], n["_ease"],
                               bool(n.get("color")))
        a, b = self.resolve(n["a"]), self.resolve(n["b"])
        return a + b if t == "add" else a * b

    def tick(self, now: float) -> List[Dict[str, Any]]:
        ev: List[Dict[str, Any]] = []
        touched: Set[int] = set()
        ended = []
        for aid in list(self.anims):
            run, ns = self.anims[aid]
            touched |= ns
            if run.update(now):
                ended.append(aid)
        self.touched = touched
        ev += self._value_events(touched)
        for aid in ended:
            ns = self.anims.pop(aid)[1]
            ev.append(self._end(aid, True, ns))
        return ev

    @property
    def active(self) -> bool:
        return bool(self.anims)

    # internals
    def _end(self, aid: int, finished: bool, ns: Set[int]) -> Dict[str, Any]:
        return {"event": "anim_end", "id": aid,
                "payload": {"finished": finished, "values": {str(n): self.values.get(n, 0.0) for n in ns}}}

    def _stop_touching(self, ns: Set[int], finished: bool) -> List[Dict[str, Any]]:
        ev = []
        for aid in [a for a, (_, an) in self.anims.items() if an & ns]:
            ev.append(self._end(aid, finished, self.anims.pop(aid)[1]))
        return ev

    def _value_events(self, touched: Set[int]) -> List[Dict[str, Any]]:
        ch = {}
        for n in touched & self.listen:
            v = self.values.get(n, 0.0)
            if self._last.get(n) != v:
                self._last[n] = v
                ch[str(n)] = v
        return [{"event": "anim_value", "id": 0, "payload": ch}] if ch else []
