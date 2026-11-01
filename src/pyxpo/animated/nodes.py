"""Animated.Value and derived nodes (interpolation, add, multiply).

A node used in a style is sent as {"$a": id}; native binds that style key to the node and keeps it updated each frame.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional

from ..ops import ANode, AListen, ASet
from ..style import parse_color
from . import runtime


class AnimatedNode:
    _is_animated = True

    def __init__(self) -> None:
        self.id = runtime.next_node_id()
        self._token: Any = None
        runtime.nodes[self.id] = self

    def _deps(self) -> List["AnimatedNode"]:
        return []

    def _spec(self) -> Dict[str, Any]:
        raise NotImplementedError

    def _register(self) -> None:
        if self._token is runtime.token():
            return
        for d in self._deps():
            d._register()
        self._token = runtime.token()
        runtime.queue(ANode(self.id, self._spec()))
        self._after_register()

    def _after_register(self) -> None:
        pass

    def _wire(self) -> Dict[str, Any]:
        self._register()
        return {"$a": self.id}

    def interpolate(self, input_range: List[float], output_range: List[Any], extrapolate: str = "extend",
                    extrapolate_left: Optional[str] = None, extrapolate_right: Optional[str] = None,
                    easing: Any = None) -> "Interpolation":
        return Interpolation(self, input_range, output_range, extrapolate_left or extrapolate,
                             extrapolate_right or extrapolate, easing)

    def __add__(self, other: Any) -> "Binary":
        return Binary("add", self, other)

    __radd__ = __add__

    def __mul__(self, other: Any) -> "Binary":
        return Binary("mul", self, other)

    __rmul__ = __mul__

    def __neg__(self) -> "Binary":
        return Binary("mul", self, -1.0)

    def __sub__(self, other: Any) -> "Binary":
        return Binary("add", self, Binary("mul", _as_node(other), -1.0))


def _as_node(x: Any) -> AnimatedNode:
    return x if isinstance(x, AnimatedNode) else Value(float(x))


class Value(AnimatedNode):
    def __init__(self, value: float = 0.0) -> None:
        super().__init__()
        self._value = float(value)
        self._listeners: Dict[int, Callable[[Dict[str, float]], None]] = {}
        self._lid = 0

    def _spec(self) -> Dict[str, Any]:
        return {"t": "value", "v": self._value}

    def _after_register(self) -> None:
        if self._listeners:
            runtime.queue(AListen(self.id, True))

    def set_value(self, value: float) -> None:
        self._value = float(value)
        if self._token is runtime.token():
            runtime.send(ASet({str(self.id): self._value}))

    def get_value(self) -> float:
        """Last value Python knows about. Stale while a native animation runs; use add_listener for live values."""
        return self._value

    def add_listener(self, cb: Callable[[Dict[str, float]], None]) -> int:
        self._lid += 1
        self._listeners[self._lid] = cb
        if len(self._listeners) == 1 and self._token is runtime.token():
            runtime.send(AListen(self.id, True))
        return self._lid

    def remove_listener(self, lid: int) -> None:
        self._listeners.pop(lid, None)
        if not self._listeners and self._token is runtime.token():
            runtime.send(AListen(self.id, False))

    def stop_animation(self, cb: Optional[Callable[[float], None]] = None) -> None:
        from .api import stop_value
        stop_value(self, cb)

    # native -> python
    def _sync(self, v: float) -> None:
        self._value = v

    def _update(self, v: float) -> None:
        self._value = v
        for cb in list(self._listeners.values()):
            cb({"value": v})

    # RN spellings
    setValue = set_value
    getValue = get_value
    addListener = add_listener
    removeListener = remove_listener
    stopAnimation = stop_animation


class ValueXY:
    """RN `Animated.ValueXY`: two Values, `.x` and `.y`, for 2D motion such as a drag. `timing`/`spring`/`decay`
    take one with a `{"x": .., "y": ..}` target and animate both."""

    def __init__(self, value: Optional[Dict[str, float]] = None) -> None:
        value = value or {}
        self.x = Value(value.get("x", 0.0))
        self.y = Value(value.get("y", 0.0))

    def set_value(self, value: Dict[str, float]) -> None:
        self.x.set_value(value["x"])
        self.y.set_value(value["y"])

    def get_value(self) -> Dict[str, float]:
        return {"x": self.x.get_value(), "y": self.y.get_value()}

    def stop_animation(self, cb: Optional[Callable[[Dict[str, float]], None]] = None) -> None:
        self.x.stop_animation()
        self.y.stop_animation()
        if cb is not None:
            cb(self.get_value())

    def get_translate_transform(self) -> List[Dict[str, Any]]:
        return [{"translateX": self.x}, {"translateY": self.y}]

    def get_layout(self) -> Dict[str, Any]:
        return {"left": self.x, "top": self.y}

    setValue = set_value
    getValue = get_value
    stopAnimation = stop_animation
    getTranslateTransform = get_translate_transform
    getLayout = get_layout


def _angle(s: str) -> float:
    s = s.strip().lower()
    if s.endswith("deg"):
        return float(s[:-3])
    if s.endswith("rad"):
        return math.degrees(float(s[:-3]))
    raise ValueError("bad angle %r" % s)


class Interpolation(AnimatedNode):
    def __init__(self, parent: AnimatedNode, inp: List[float], out: List[Any], left: str, right: str,
                 easing: Any) -> None:
        super().__init__()
        if len(inp) != len(out) or len(inp) < 2:
            raise ValueError("interpolate needs input_range and output_range of equal length >= 2")
        if any(b < a for a, b in zip(inp, inp[1:])):
            raise ValueError("input_range must be non-decreasing")
        for e in (left, right):
            if e not in ("extend", "clamp", "identity"):
                raise ValueError("bad extrapolate %r" % e)
        if easing is not None and not isinstance(easing, dict):
            raise ValueError("interpolate easing must be a pyxpo Easing spec")
        self.parent, self.inp, self.ex, self.easing = parent, [float(x) for x in inp], [left, right], easing
        self.color = any(isinstance(o, str) and not o.strip().lower().endswith(("deg", "rad")) for o in out)
        if self.color:
            self.out: List[Any] = [parse_color(o) for o in out]
        else:
            self.out = [_angle(o) if isinstance(o, str) else float(o) for o in out]

    def _deps(self) -> List[AnimatedNode]:
        return [self.parent]

    def _spec(self) -> Dict[str, Any]:
        return {"t": "interp", "src": self.parent.id, "in": self.inp, "out": self.out, "ex": self.ex,
                "color": self.color, "easing": self.easing}


class Binary(AnimatedNode):
    def __init__(self, kind: str, a: Any, b: Any) -> None:
        super().__init__()
        self.kind, self.a, self.b = kind, _as_node(a), _as_node(b)

    def _deps(self) -> List[AnimatedNode]:
        return [self.a, self.b]

    def _spec(self) -> Dict[str, Any]:
        return {"t": self.kind, "a": self.a.id, "b": self.b.id}
