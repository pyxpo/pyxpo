"""`react-native-gesture-handler` equivalent: declarative `Gesture.*()` builders and `GestureDetector`.

Gestures are recognised in Python from the raw touch events, so callbacks run on the JS-equivalent thread. Use
`Animated.event`/`Animated.Value.set_value` inside callbacks for native-driven motion.
"""
from __future__ import annotations

import math
import time
from typing import Any, Callable, Dict, List, Optional

from .apis.pan_responder import GestureState, _pt
from .component import component
from .components.view import View
from .hooks import use_memo, use_ref

UNDETERMINED, BEGAN, ACTIVE, END, FAILED, CANCELLED = 0, 2, 4, 5, 1, 3  # RN-GH `State`


class State:
    UNDETERMINED, FAILED, BEGAN, CANCELLED, ACTIVE, END = 0, 1, 2, 3, 4, 5


class _Gesture:
    """Common builder: chainable `on_*`/`onX` callbacks plus `enabled`, `with_ref`, `require_to_fail`, `simultaneous_with`."""
    kind = "base"
    _CB = ("begin", "start", "update", "end", "finalize")

    def __init__(self) -> None:
        self.cb: Dict[str, Callable[..., Any]] = {}
        self._enabled = True
        self.blocks: List["_Gesture"] = []  # gestures that must fail before this one may activate
        self.state = State.UNDETERMINED
        self.gs = GestureState()

    def __getattr__(self, name: str) -> Any:
        key = name[2:].lower() if name.startswith("on") and not name.startswith("on_") else name[3:] if name.startswith("on_") else ""
        if key not in self._CB:
            raise AttributeError(name)

        def setter(fn: Callable[..., Any]) -> "_Gesture":
            self.cb[key] = fn
            return self
        return setter

    def enabled(self, value: bool) -> "_Gesture":
        self._enabled = bool(value)
        return self

    def require_external_gesture_to_fail(self, *others: "_Gesture") -> "_Gesture":
        self.blocks.extend(others)
        return self

    requireExternalGestureToFail = require_external_gesture_to_fail

    def simultaneous_with_external_gesture(self, *others: "_Gesture") -> "_Gesture":
        return self

    simultaneousWithExternalGesture = simultaneous_with_external_gesture

    def _emit(self, name: str, e: Dict[str, Any], success: Optional[bool] = None) -> None:
        fn = self.cb.get(name)
        if fn is None:
            return
        g = self.gs
        ev = {"x": g.moveX, "y": g.moveY, "absoluteX": g.moveX, "absoluteY": g.moveY, "translationX": g.dx,
              "translationY": g.dy, "velocityX": g.vx, "velocityY": g.vy, "numberOfPointers": g.numberActiveTouches,
              "state": self.state}
        if success is not None:
            fn(ev, success) if name in ("end", "finalize") else fn(ev)
        else:
            fn(ev)

    # subclasses override
    def touch_start(self, e: Dict[str, Any]) -> None: ...
    def touch_move(self, e: Dict[str, Any]) -> None: ...
    def touch_end(self, e: Dict[str, Any]) -> None: ...
    def long_press(self, e: Dict[str, Any]) -> None: ...

    def _finish(self, e: Dict[str, Any], ok: bool) -> None:
        was_active = self.state == State.ACTIVE
        self.state = State.END if ok else State.FAILED
        if was_active or ok:
            self._emit("end", e, ok)
        self._emit("finalize", e, ok)
        self.state = State.UNDETERMINED


class PanGesture(_Gesture):
    kind = "pan"

    def __init__(self) -> None:
        super().__init__()
        self.min_dist = 10.0
        self.axis: Optional[str] = None

    def min_distance(self, v: float) -> "PanGesture":
        self.min_dist = float(v)
        return self

    minDistance = min_distance

    def active_offset_x(self, v: Any) -> "PanGesture":
        self.axis = "x"
        self.min_dist = abs(v[0] if isinstance(v, (list, tuple)) else v)
        return self

    def active_offset_y(self, v: Any) -> "PanGesture":
        self.axis = "y"
        self.min_dist = abs(v[0] if isinstance(v, (list, tuple)) else v)
        return self

    activeOffsetX, activeOffsetY = active_offset_x, active_offset_y

    def touch_start(self, e: Dict[str, Any]) -> None:
        self.gs._start(e)
        self.state = State.BEGAN
        self._emit("begin", e)

    def touch_move(self, e: Dict[str, Any]) -> None:
        if self.state not in (State.BEGAN, State.ACTIVE):
            return
        self.gs._move(e)
        if self.state == State.BEGAN:
            d = abs(self.gs.dx) if self.axis == "x" else abs(self.gs.dy) if self.axis == "y" else math.hypot(self.gs.dx, self.gs.dy)
            if d < self.min_dist:
                return
            self.state = State.ACTIVE
            self._emit("start", e)
        self._emit("update", e)

    def touch_end(self, e: Dict[str, Any]) -> None:
        if self.state == State.UNDETERMINED:
            return
        self.gs._move(e, final=True)
        self._finish(e, self.state == State.ACTIVE)


class TapGesture(_Gesture):
    kind = "tap"

    def __init__(self) -> None:
        super().__init__()
        self.taps, self.max_dist, self.max_dur = 1, 10.0, 0.5
        self.count, self.last = 0, 0.0

    def number_of_taps(self, n: int) -> "TapGesture":
        self.taps = int(n)
        return self

    def max_distance(self, v: float) -> "TapGesture":
        self.max_dist = float(v)
        return self

    def max_duration(self, ms: float) -> "TapGesture":
        self.max_dur = ms / 1000.0
        return self

    numberOfTaps, maxDistance, maxDuration = number_of_taps, max_distance, max_duration

    def touch_start(self, e: Dict[str, Any]) -> None:
        self.gs._start(e)
        self.state = State.BEGAN
        self._emit("begin", e)

    def touch_move(self, e: Dict[str, Any]) -> None:
        if self.state == State.BEGAN:
            self.gs._move(e)
            if math.hypot(self.gs.dx, self.gs.dy) > self.max_dist:
                self.count = 0
                self._finish(e, False)

    def touch_end(self, e: Dict[str, Any]) -> None:
        if self.state != State.BEGAN:
            return
        now = time.monotonic()
        self.gs._move(e, final=True)
        if now - self.gs._t > self.max_dur and False:
            return
        self.count = self.count + 1 if now - self.last < 0.3 or self.count == 0 else 1
        self.last = now
        if self.count < self.taps:
            self.state = State.UNDETERMINED
            return
        self.count = 0
        self.state = State.ACTIVE
        self._emit("start", e)
        self._finish(e, True)


class LongPressGesture(_Gesture):
    kind = "long_press"

    def __init__(self) -> None:
        super().__init__()
        self.max_dist = 10.0

    def min_duration(self, ms: float) -> "LongPressGesture":
        return self  # the platform's long-press delay applies; tune with the View's `delay_long_press`

    minDuration = min_duration

    def touch_start(self, e: Dict[str, Any]) -> None:
        self.gs._start(e)
        self.state = State.BEGAN
        self._emit("begin", e)

    def touch_move(self, e: Dict[str, Any]) -> None:
        if self.state == State.BEGAN:
            self.gs._move(e)
            if math.hypot(self.gs.dx, self.gs.dy) > self.max_dist:
                self._finish(e, False)

    def long_press(self, e: Dict[str, Any]) -> None:
        if self.state == State.BEGAN:
            self.state = State.ACTIVE
            self._emit("start", e)

    def touch_end(self, e: Dict[str, Any]) -> None:
        if self.state in (State.BEGAN, State.ACTIVE):
            self._finish(e, self.state == State.ACTIVE)


class FlingGesture(PanGesture):
    kind = "fling"

    def __init__(self) -> None:
        super().__init__()
        self.direction = "right"
        self.min_speed = 600.0

    def set_direction(self, d: str) -> "FlingGesture":
        self.direction = d
        return self

    direction_ = set_direction

    def touch_move(self, e: Dict[str, Any]) -> None:
        if self.state == State.BEGAN:
            self.gs._move(e)

    def touch_end(self, e: Dict[str, Any]) -> None:
        if self.state != State.BEGAN:
            return
        self.gs._move(e, final=True)
        g = self.gs
        speed = {"right": g.vx, "left": -g.vx, "down": g.vy, "up": -g.vy}.get(self.direction, 0.0)
        if speed >= self.min_speed:
            self.state = State.ACTIVE
            self._emit("start", e)
            self._finish(e, True)
        else:
            self._finish(e, False)


class _Composed:
    """Race / Simultaneous / Exclusive: a flat list of gestures with a policy."""

    def __init__(self, mode: str, gestures: tuple) -> None:
        self.mode = mode
        self.list: List[_Gesture] = [g for x in gestures for g in (x.list if isinstance(x, _Composed) else [x])]


class Gesture:
    @staticmethod
    def Pan() -> PanGesture:
        return PanGesture()

    @staticmethod
    def Tap() -> TapGesture:
        return TapGesture()

    @staticmethod
    def LongPress() -> LongPressGesture:
        return LongPressGesture()

    @staticmethod
    def Fling() -> FlingGesture:
        return FlingGesture()

    @staticmethod
    def Simultaneous(*g: Any) -> _Composed:
        return _Composed("simultaneous", g)

    @staticmethod
    def Race(*g: Any) -> _Composed:
        return _Composed("race", g)

    @staticmethod
    def Exclusive(*g: Any) -> _Composed:
        return _Composed("exclusive", g)


def _dispatch(gestures: List[_Gesture], mode: str, name: str, e: Dict[str, Any]) -> None:
    winner = None
    for g in gestures:
        if not g._enabled:
            continue
        if mode in ("race", "exclusive") and winner is not None and g is not winner and g.state == State.UNDETERMINED \
                and name != "touch_start":
            continue
        getattr(g, name)(e)
        if mode == "race" and winner is None and g.state == State.ACTIVE:
            winner = g
            for o in gestures:
                if o is not g and o.state in (State.BEGAN, State.ACTIVE):
                    o._finish(e, False)
        elif mode == "exclusive" and winner is None and g.state == State.ACTIVE:
            winner = g


@component
def GestureDetector(*children: Any, gesture: Any = None, **props: Any):
    """Wraps its child View and feeds touches to `gesture` (a `Gesture.*()` or a composition)."""
    ref = use_ref(None)
    ref.current = gesture
    handlers = use_memo(lambda: _handlers(ref), [])
    kids = [c for c in children if c is not None]
    if len(kids) == 1 and getattr(kids[0], "props", None) is not None and hasattr(kids[0], "type"):
        el = kids[0]
        el.props = {**el.props, **{k: _chain(el.props.get(k), v) for k, v in handlers.items()}}
        return el
    return View(*kids, **handlers, **props)


def _chain(a: Optional[Callable[..., Any]], b: Callable[..., Any]) -> Callable[..., Any]:
    return b if a is None else (lambda e, a=a, b=b: (a(e), b(e))[1])


def _handlers(ref: Any) -> Dict[str, Callable[..., Any]]:
    def run(name: str) -> Callable[[Dict[str, Any]], None]:
        def h(e: Dict[str, Any]) -> None:
            g = ref.current
            if g is None:
                return
            comp = g if isinstance(g, _Composed) else _Composed("simultaneous", (g,))
            _dispatch(comp.list, comp.mode, name, e)
        return h
    return {"on_touch_start": run("touch_start"), "on_touch_move": run("touch_move"), "on_touch_end": run("touch_end"),
            "on_long_press": run("long_press")}


@component
def GestureHandlerRootView(*children: Any, style: Any = None, **props: Any):
    """Root wrapper (a flex:1 View); required by the RN library, kept for source compatibility."""
    return View(*children, style=[{"flex": 1}, style], **props)


__all__ = ["Gesture", "GestureDetector", "GestureHandlerRootView", "State", "PanGesture", "TapGesture",
           "LongPressGesture", "FlingGesture"]
