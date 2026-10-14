"""Device environment: window size, density, color scheme, insets, keyboard.

Native sends a full snapshot at startup (`hello` handshake) and an `env` event on every change.
All sizes are dp/pt. Hooks re-render the component when the part they read changes.
"""
from __future__ import annotations

import copy
from typing import Any, Callable, Dict, List, Optional

from .hooks import use_effect, use_state

BREAKPOINTS = (("sm", 0), ("md", 600), ("lg", 840))  # width in dp, ascending

DEFAULT_ENV: Dict[str, Any] = {
    "os": "desktop",
    "window": {"width": 360.0, "height": 640.0},
    "screen": {"width": 360.0, "height": 640.0},
    "scale": 1.0,
    "font_scale": 1.0,
    "color_scheme": "light",
    "insets": {"top": 0.0, "right": 0.0, "bottom": 0.0, "left": 0.0},
    "keyboard": {"visible": False, "height": 0.0},
}


def _merge(base: Dict[str, Any], upd: Dict[str, Any]) -> Dict[str, Any]:
    for k, v in upd.items():
        if k not in base:
            continue  # ignore unknown keys: forward compatible with newer native
        if isinstance(base[k], dict) and isinstance(v, dict):
            for kk, vv in v.items():
                if kk in base[k]:
                    base[k][kk] = vv
        else:
            base[k] = v
    return base


class Env:
    def __init__(self, snapshot: Optional[Dict[str, Any]] = None) -> None:
        self._data: Dict[str, Any] = copy.deepcopy(DEFAULT_ENV)
        self._listeners: List[Callable[[], None]] = []
        if snapshot:
            _merge(self._data, snapshot)

    def get(self) -> Dict[str, Any]:
        return copy.deepcopy(self._data)

    def update(self, upd: Dict[str, Any]) -> bool:
        before = copy.deepcopy(self._data)
        _merge(self._data, upd)
        if before == self._data:
            return False
        for fn in list(self._listeners):
            fn()
        return True

    def subscribe(self, fn: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(fn)

        def off() -> None:
            if fn in self._listeners:
                self._listeners.remove(fn)

        return off

    # convenience readers
    @property
    def width(self) -> float:
        return self._data["window"]["width"]

    @property
    def height(self) -> float:
        return self._data["window"]["height"]


current = Env()  # replaced by App on creation; module-level readers use it


def set_current(env: Env) -> None:
    global current
    current = env


# -- React-Native-style statics -------------------------------------------
class _Subscription:
    def __init__(self, off: Callable[[], None]) -> None:
        self._off = off

    def remove(self) -> None:
        self._off()


class Dimensions:
    @staticmethod
    def get(which: str = "window") -> Dict[str, float]:
        if which not in ("window", "screen"):
            raise ValueError("Dimensions.get: 'window' or 'screen', got %r" % (which,))
        d = current._data
        return {"width": d[which]["width"], "height": d[which]["height"], "scale": d["scale"],
                "font_scale": d["font_scale"], "fontScale": d["font_scale"]}

    @staticmethod
    def add_event_listener(event: str, fn: Callable[[Dict[str, Any]], Any]) -> Any:
        """`fn({"window", "screen"})` on every size change. Returns a subscription with `.remove()`."""
        if event != "change":
            raise ValueError("Dimensions.add_event_listener: only 'change', got %r" % (event,))
        last = [Dimensions.get("window"), Dimensions.get("screen")]

        def on_env() -> None:
            now = [Dimensions.get("window"), Dimensions.get("screen")]
            if now != last:
                last[:] = now
                fn({"window": now[0], "screen": now[1]})

        return _Subscription(current.subscribe(on_env))

    addEventListener = add_event_listener


class PixelRatio:
    @staticmethod
    def get() -> float:
        return current._data["scale"]

    @staticmethod
    def get_font_scale() -> float:
        return current._data["font_scale"]

    @staticmethod
    def get_pixel_size_for_layout_size(dp: float) -> int:
        return int(round(dp * current._data["scale"]))

    @staticmethod
    def round_to_nearest_pixel(dp: float) -> float:
        s = current._data["scale"]
        return round(dp * s) / s


class _PlatformMeta(type):
    @property
    def OS(cls) -> str:
        return current._data["os"]

    @property
    def Version(cls) -> Any:
        return current._data.get("os_version")


class Platform(metaclass=_PlatformMeta):
    """`Platform.OS` ("android" | "ios" | ...), `Platform.os()`, `Platform.select({...})`."""

    @staticmethod
    def os() -> str:
        return current._data["os"]

    @staticmethod
    def select(spec: Dict[str, Any]) -> Any:
        o = current._data["os"]
        if o in spec:
            return spec[o]
        if "native" in spec and o in ("android", "ios"):
            return spec["native"]
        return spec.get("default")


# -- responsive helpers ---------------------------------------------------
def breakpoint_for(width: float) -> str:
    name = BREAKPOINTS[0][0]
    for n, minw in BREAKPOINTS:
        if width >= minw:
            name = n
    return name


def responsive(bp: str, values: Dict[str, Any], default: Any = None) -> Any:
    """Pick the value for breakpoint `bp`, falling back to the next smaller one that is defined."""
    names = [n for n, _ in BREAKPOINTS]
    i = names.index(bp)
    while i >= 0:
        if names[i] in values:
            return values[names[i]]
        i -= 1
    return default


def orientation(window: Dict[str, float]) -> str:
    return "landscape" if window["width"] > window["height"] else "portrait"


# -- hooks ------------------------------------------------------------------
def _use_env(select: Callable[[Dict[str, Any]], Any]) -> Any:
    """Re-render only when select(env) changes."""
    from .hooks import _current  # same package; avoids a public API for this
    env = _current("use_env").rec.env
    value, set_value = use_state(lambda: select(env.get()))

    def sub() -> Callable[[], None]:
        set_value(select(env.get()))  # env may have changed between render and effect
        return env.subscribe(lambda: set_value(select(env.get())))

    use_effect(sub, [id(env)])
    return value


def use_window_dimensions() -> Dict[str, Any]:
    return _use_env(lambda e: {"width": e["window"]["width"], "height": e["window"]["height"],
                               "scale": e["scale"], "font_scale": e["font_scale"]})


def use_color_scheme() -> str:
    return _use_env(lambda e: e["color_scheme"])


def use_safe_area_insets() -> Dict[str, float]:
    return _use_env(lambda e: dict(e["insets"]))


def use_keyboard() -> Dict[str, Any]:
    return _use_env(lambda e: dict(e["keyboard"]))


def use_orientation() -> str:
    return _use_env(lambda e: orientation(e["window"]))


def use_breakpoint() -> str:
    return _use_env(lambda e: breakpoint_for(e["window"]["width"]))


def use_responsive(values: Dict[str, Any], default: Any = None) -> Any:
    return responsive(use_breakpoint(), values, default)
