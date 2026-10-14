"""PanResponder.create: RN gesture responder on top of the raw touch events."""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional


def _pt(e: Dict[str, Any], axis: str) -> float:
    v = e.get("page_" + axis)
    return float(e.get(axis, 0.0) if v is None else v)


class GestureState:
    """RN `gestureState`: moveX/moveY (current), x0/y0 (start), dx/dy (since start), vx/vy (dp per second)."""

    def __init__(self) -> None:
        self.x0 = self.y0 = self.moveX = self.moveY = 0.0
        self.dx = self.dy = self.vx = self.vy = 0.0
        self.numberActiveTouches = 0
        self._t = 0.0

    def _start(self, e: Dict[str, Any]) -> None:
        self.x0 = self.moveX = _pt(e, "x")
        self.y0 = self.moveY = _pt(e, "y")
        self.dx = self.dy = self.vx = self.vy = 0.0
        self.numberActiveTouches = 1
        self._t = time.monotonic()

    def _move(self, e: Dict[str, Any], final: bool = False) -> None:
        x, y, now = _pt(e, "x"), _pt(e, "y"), time.monotonic()
        dt = now - self._t
        if final:
            self.numberActiveTouches = 0
            if x == self.moveX and y == self.moveY:
                return  # release at the last move point: keep the fling velocity instead of zeroing it
        if dt > 0:
            self.vx, self.vy = (x - self.moveX) / dt, (y - self.moveY) / dt
        self.moveX, self.moveY, self._t = x, y, now
        self.dx, self.dy = x - self.x0, y - self.y0


class _PanResponder:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.state = GestureState()
        self.panHandlers = {"on_touch_start": self._start, "on_touch_move": self._move, "on_touch_end": self._end}

    def _call(self, name: str, e: Dict[str, Any]) -> None:
        fn = self.config.get(name)
        if fn is not None:
            fn(e, self.state)

    def _start(self, e: Dict[str, Any]) -> None:
        self.state._start(e)
        self._call("onPanResponderGrant", e)

    def _move(self, e: Dict[str, Any]) -> None:
        self.state._move(e)
        self._call("onPanResponderMove", e)

    def _end(self, e: Dict[str, Any]) -> None:
        self.state._move(e, final=True)
        self._call("onPanResponderRelease", e)
        self._call("onPanResponderEnd", e)


class PanResponder:
    @staticmethod
    def create(config: Dict[str, Any]) -> _PanResponder:
        """`config`: `onPanResponderGrant/Move/Release/End(event, gestureState)`. Spread `.panHandlers` on a View:
        `View(**pan.panHandlers)`."""
        return _PanResponder(config)
