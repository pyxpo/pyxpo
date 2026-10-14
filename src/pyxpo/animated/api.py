"""Animated.timing / spring / decay and composition (sequence, parallel, stagger, loop, delay)."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from ..ops import Animate, AStop
from . import easing as easing_mod
from . import runtime
from .nodes import AnimatedNode, Value


class Animation:
    """A description of motion. Nothing runs until `start()`."""

    def __init__(self) -> None:
        self._aid: Optional[int] = None
        self._native_aid = True

    # subclass API
    def _spec(self) -> Dict[str, Any]:
        raise NotImplementedError

    def _values(self) -> List[Value]:
        return []

    def _native(self) -> bool:
        return True

    def start(self, callback: Optional[Callable[[Dict[str, Any]], None]] = None) -> None:
        spec, vals = self._spec(), self._values()
        aid = runtime.next_anim_id()
        self._aid = aid
        if callback is not None:
            runtime.callbacks[aid] = callback
        if self._native():
            for v in vals:
                v._register()
            runtime.send(Animate(aid, spec))
        else:
            runtime.py_start(aid, spec, vals)
        self._native_aid = self._native()

    def stop(self) -> None:
        if self._aid is None:
            return
        if self._native_aid:
            runtime.send(AStop(self._aid))
        else:
            runtime.py_stop(self._aid)

    def run(self) -> Any:
        """Awaitable form: `finished = await anim.run()`."""
        loop = runtime._app.loop
        fut = loop.create_future()
        self.start(lambda r: fut.done() or fut.set_result(r["finished"]))
        return fut


class _Leaf(Animation):
    def __init__(self, value: Value, spec: Dict[str, Any], native: bool) -> None:
        super().__init__()
        self.value, self.s, self.nat = value, spec, native

    def _spec(self) -> Dict[str, Any]:
        return dict(self.s, node=self.value.id)

    def _values(self) -> List[Value]:
        return [self.value]

    def _native(self) -> bool:
        return self.nat


class _Group(Animation):
    def __init__(self, kind: str, items: List[Animation], **extra: Any) -> None:
        super().__init__()
        self.kind, self.items, self.extra = kind, items, extra

    def _spec(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"t": self.kind}
        if self.kind == "loop":
            d["item"] = self.items[0]._spec()
        else:
            d["items"] = [i._spec() for i in self.items]
        d.update(self.extra)
        return d

    def _values(self) -> List[Value]:
        out: List[Value] = []
        for i in self.items:
            out.extend(i._values())
        return out

    def _native(self) -> bool:
        return all(i._native() for i in self.items)


class _Delay(Animation):
    def __init__(self, ms: float) -> None:
        super().__init__()
        self.ms = ms

    def _spec(self) -> Dict[str, Any]:
        return {"t": "delay", "ms": self.ms}


def _check(value: Any) -> None:
    if not isinstance(value, Value):
        raise TypeError("only Animated.Value can be animated, got %s" % type(value).__name__)


def _with_delay(a: Animation, delay: float) -> Animation:
    return _Group("seq", [_Delay(delay), a]) if delay else a


def timing(value: Value, to_value: float, duration: float = 300, easing: Any = None, delay: float = 0,
           use_native_driver: bool = True) -> Animation:
    _check(value)
    nat = use_native_driver and easing_mod.is_native(easing)
    s = {"t": "timing", "to": float(to_value), "ms": float(duration), "easing": easing if nat else easing}
    return _with_delay(_Leaf(value, s, nat), delay)


def spring(value: Value, to_value: float, stiffness: float = 100, damping: float = 10, mass: float = 1,
           velocity: Optional[float] = None, overshoot_clamping: bool = False,
           rest_displacement_threshold: float = 0.001, rest_speed_threshold: float = 0.001, delay: float = 0,
           use_native_driver: bool = True) -> Animation:
    _check(value)
    s = {"t": "spring", "to": float(to_value), "k": float(stiffness), "c": float(damping), "m": float(mass),
         "v0": velocity, "clamp": overshoot_clamping, "rest_d": rest_displacement_threshold,
         "rest_v": rest_speed_threshold}
    return _with_delay(_Leaf(value, s, use_native_driver), delay)


def decay(value: Value, velocity: Optional[float] = None, deceleration: float = 0.998, delay: float = 0,
          use_native_driver: bool = True) -> Animation:
    """`velocity` in units per ms (like React Native). None continues the value's current velocity."""
    _check(value)
    s = {"t": "decay", "v0": velocity, "decel": deceleration}
    return _with_delay(_Leaf(value, s, use_native_driver), delay)


def delay(ms: float) -> Animation:
    return _Delay(ms)


def sequence(animations: List[Animation]) -> Animation:
    return _Group("seq", list(animations))


def parallel(animations: List[Animation]) -> Animation:
    return _Group("par", list(animations))


def stagger(ms: float, animations: List[Animation]) -> Animation:
    return _Group("par", [_Group("seq", [_Delay(ms * i), a]) if i else a for i, a in enumerate(animations)])


def loop(animation: Animation, iterations: int = -1, reset_before_iteration: bool = True) -> Animation:
    return _Group("loop", [animation], n=iterations, reset=reset_before_iteration)


def stop_value(value: Value, cb: Optional[Callable[[float], None]]) -> None:
    from ..ops import ASet
    runtime.py_aset(value.id, value._value)
    if value._token is runtime.token():
        runtime.send(ASet({str(value.id): value._value}))
    if cb is not None:
        cb(value._value)


class Animated:
    Value = Value
    timing = staticmethod(timing)
    spring = staticmethod(spring)
    decay = staticmethod(decay)
    delay = staticmethod(delay)
    sequence = staticmethod(sequence)
    parallel = staticmethod(parallel)
    stagger = staticmethod(stagger)
    loop = staticmethod(loop)
