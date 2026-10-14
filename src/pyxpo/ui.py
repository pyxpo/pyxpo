"""Interactive components built in Python on top of View: Pressable, Switch, Checkbox.

They draw with the box painter and react to the native press_in/press_out/press/long_press events,
so every colour, size and radius is a style the app can override.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from .component import component
from .element import Text, View, _Modal
from .hooks import use_memo, use_ref, use_state
from .style import flatten

_A11Y = ("accessible", "accessibility_label", "accessibility_hint", "accessibility_role", "accessibility_state",
         "accessibility_value")


def _a11y(props: Dict[str, Any]) -> Dict[str, Any]:
    return {k: props[k] for k in _A11Y if k in props}


@component
def Pressable(*children: Any, on_press: Optional[Callable[[], Any]] = None,
              on_long_press: Optional[Callable[[], Any]] = None,
              on_press_in: Optional[Callable[[], Any]] = None,
              on_press_out: Optional[Callable[[], Any]] = None,
              disabled: bool = False, style: Any = None, render: Optional[Callable[[bool], Any]] = None,
              pressed_style: Any = None,
              pressed_opacity: float = 0.6, **props: Any):
    """Touchable View. `style` may be a callable taking `pressed`; `render(pressed)` returns the children."""
    pressed, set_pressed = use_state(False)
    base = style(pressed) if callable(style) else style
    st = flatten(base)
    if pressed and not disabled:
        if pressed_style is not None:
            st = {**st, **flatten(pressed_style)}
        elif not callable(style) and pressed_opacity is not None:
            st = {**st, "opacity": st.get("opacity", 1.0) * pressed_opacity}
    if disabled:
        st = {**st, "opacity": st.get("opacity", 1.0) * 0.4}
    kids = [render(pressed)] if render else list(children)
    extra: Dict[str, Any] = _a11y(props)
    if disabled:
        extra["accessibility_state"] = {**extra.get("accessibility_state", {}), "disabled": True}
    if not disabled:
        if on_press is not None:
            extra["on_press"] = on_press
        if on_long_press is not None:
            extra["on_long_press"] = on_long_press
        extra["on_press_in"] = lambda *a: (set_pressed(True), on_press_in and on_press_in())[0]
        extra["on_press_out"] = lambda *a: (set_pressed(False), on_press_out and on_press_out())[0]
    return View(*kids, style=st, **extra)


@component
def Switch(value: bool = False, on_value_change: Optional[Callable[[bool], Any]] = None, disabled: bool = False,
           track_color: Optional[Dict[str, Any]] = None, thumb_color: Any = "#ffffff",
           width: float = 52, height: float = 32, style: Any = None, **props: Any):
    tc = {"off": "#c7c7cc", "on": "#34c759", **(track_color or {})}
    pad = 2
    knob = height - 2 * pad
    track = {"width": width, "height": height, "border_radius": height / 2, "padding": pad,
             "background_color": tc["on"] if value else tc["off"], "flex_direction": "row",
             "justify_content": "flex-end" if value else "flex-start", "align_items": "center"}
    thumb = {"width": knob, "height": knob, "border_radius": knob / 2, "background_color": thumb_color,
             "shadow_color": "#000000", "shadow_opacity": 0.25, "shadow_radius": 2, "shadow_offset_y": 1}
    return Pressable(View(style=thumb), disabled=disabled, style=[track, style],
                     on_press=lambda: on_value_change(not value) if on_value_change else None,
                     pressed_opacity=0.85,
                     **{"accessibility_role": "switch", "accessibility_state": {"checked": bool(value)}, **_a11y(props)})


@component
def Checkbox(value: bool = False, on_value_change: Optional[Callable[[bool], Any]] = None, disabled: bool = False,
             size: float = 24, color: Any = "#007aff", check_color: Any = "#ffffff", radius: float = 6,
             style: Any = None, **props: Any):
    box = {"width": size, "height": size, "border_radius": radius, "border_width": 2, "border_color": color,
           "background_color": color if value else "transparent", "align_items": "center",
           "justify_content": "center"}
    return Pressable(Text("✓", style={"color": check_color, "font_size": size * 0.7, "font_weight": "bold"})
                     if value else None,
                     disabled=disabled, style=[box, style],
                     on_press=lambda: on_value_change(not value) if on_value_change else None,
                     **{"accessibility_role": "checkbox", "accessibility_state": {"checked": bool(value)}, **_a11y(props)})


@component
def SafeArea(*children: Any, edges: Any = ("top", "right", "bottom", "left"), avoid_keyboard: bool = False,
             style: Any = None, **props: Any):
    """View padded by the system insets (status bar, notch, home indicator). With `avoid_keyboard` the bottom
    padding grows to the keyboard height while the keyboard is open."""
    from .env import use_keyboard, use_safe_area_insets
    ins = use_safe_area_insets()
    kb = use_keyboard()
    pad = {e: ins[e] for e in edges}
    if avoid_keyboard and "bottom" in pad:
        pad["bottom"] = max(pad["bottom"], kb["height"])
    base = {"flex": 1, **{"padding_" + k: v for k, v in pad.items()}}
    # explicit padding in `style` is added on top of the inset
    st = flatten(style)
    for k, v in pad.items():
        key = "padding_" + k
        extra = st.get(key, st.get("padding_vertical" if k in ("top", "bottom") else "padding_horizontal",
                                   st.get("padding", 0)))
        if isinstance(extra, (int, float)):
            base[key] = v + extra
    st = {**st, **base}
    for k in ("padding", "padding_vertical", "padding_horizontal"):
        st.pop(k, None)
    return View(*children, style=st, **props)


@component
def KeyboardAvoidingView(*children: Any, offset: float = 0.0, style: Any = None, **props: Any):
    """View whose bottom padding follows the keyboard height (minus `offset`)."""
    from .env import use_keyboard
    kb = use_keyboard()
    st = flatten(style)
    extra = st.get("padding_bottom", st.get("padding_vertical", st.get("padding", 0)))
    st = {**st, "padding_bottom": max(0.0, kb["height"] - offset) + (extra if isinstance(extra, (int, float)) else 0)}
    return View(*children, style=st, **props)


@component
def Slider(value: float = 0.0, minimum: float = 0.0, maximum: float = 1.0, step: float = 0.0,
           on_value_change: Optional[Callable[[float], Any]] = None,
           on_sliding_complete: Optional[Callable[[float], Any]] = None, disabled: bool = False,
           min_track_color: Any = "#007aff", max_track_color: Any = "#c7c7cc", thumb_color: Any = "#ffffff",
           thumb_size: float = 28, track_height: float = 4, style: Any = None, **props: Any):
    """Horizontal slider driven by native touch events. Controlled: pass `value`, update it in `on_value_change`."""
    width, set_width = use_state(0.0)
    span = float(maximum - minimum) or 1.0
    usable = max(1.0, width - thumb_size)
    frac = min(1.0, max(0.0, (value - minimum) / span))

    def at(x: float) -> float:
        f = min(1.0, max(0.0, (x - thumb_size / 2) / usable))
        v = minimum + f * span
        if step:
            v = minimum + round((v - minimum) / step) * step
        return min(float(maximum), max(float(minimum), v))

    def layout(e: Dict[str, Any]) -> None:
        if e["width"] != width:
            set_width(float(e["width"]))

    def move(e: Dict[str, Any]) -> None:
        if on_value_change is not None:
            on_value_change(at(e["x"]))

    def end(e: Dict[str, Any]) -> None:
        if on_sliding_complete is not None:
            on_sliding_complete(at(e["x"]))

    base = {"height": thumb_size, "justify_content": "center", "opacity": 0.4 if disabled else 1.0}
    track = {"position": "absolute", "left": thumb_size / 2, "right": thumb_size / 2, "height": track_height,
             "border_radius": track_height / 2, "background_color": max_track_color}
    fill = {"position": "absolute", "left": thumb_size / 2, "width": frac * usable, "height": track_height,
            "border_radius": track_height / 2, "background_color": min_track_color}
    thumb = {"position": "absolute", "left": frac * usable, "width": thumb_size, "height": thumb_size,
             "border_radius": thumb_size / 2, "background_color": thumb_color, "shadow_color": "#000000",
             "shadow_opacity": 0.25, "shadow_radius": 2, "shadow_offset_y": 1}
    touch: Dict[str, Any] = {} if disabled else {"on_touch_start": move, "on_touch_move": move, "on_touch_end": end}
    return View(View(style=track), View(style=fill), View(style=thumb), style=[base, style], on_layout=layout,
                **{"accessibility_role": "adjustable", "accessibility_value": str(round(value, 3)), **_a11y(props)},
                **touch)


def _pt(e: Dict[str, Any], axis: str) -> float:
    v = e.get("page_" + axis)
    return float(e.get(axis, 0.0) if v is None else v)


class Gesture:
    """PanResponder state: dx/dy since touch start (dp), vx/vy velocity (dp/s), x0/y0 start, x/y current."""

    def __init__(self) -> None:
        self.x0 = self.y0 = self.x = self.y = 0.0
        self.dx = self.dy = self.vx = self.vy = 0.0
        self._t = 0.0

    def _start(self, e: Dict[str, Any]) -> None:
        self.x0 = self.x = _pt(e, "x")
        self.y0 = self.y = _pt(e, "y")
        self.dx = self.dy = self.vx = self.vy = 0.0
        self._t = time.monotonic()

    def _move(self, e: Dict[str, Any], final: bool = False) -> None:
        x, y, now = _pt(e, "x"), _pt(e, "y"), time.monotonic()
        dt = now - self._t
        if final and x == self.x and y == self.y:
            return  # release at the last move point: keep the fling velocity instead of zeroing it
        if dt > 0:
            self.vx, self.vy = (x - self.x) / dt, (y - self.y) / dt
        self.x, self.y, self._t = x, y, now
        self.dx, self.dy = x - self.x0, y - self.y0


def use_pan_responder(on_start: Optional[Callable[[Gesture], Any]] = None,
                      on_move: Optional[Callable[[Gesture], Any]] = None,
                      on_end: Optional[Callable[[Gesture], Any]] = None) -> Dict[str, Any]:
    """Props to spread on a View (`View(**pan)`) to track a drag. Callbacks get a [Gesture]."""
    g = use_ref(None)
    if g.current is None:
        g.current = Gesture()
    fns = use_ref(None)
    fns.current = (on_start, on_move, on_end)  # latest callbacks without changing the handler identity

    def start(e: Dict[str, Any]) -> None:
        g.current._start(e)
        if fns.current[0]:
            fns.current[0](g.current)

    def move(e: Dict[str, Any]) -> None:
        g.current._move(e)
        if fns.current[1]:
            fns.current[1](g.current)

    def end(e: Dict[str, Any]) -> None:
        g.current._move(e, final=True)
        if fns.current[2]:
            fns.current[2](g.current)

    return {"on_touch_start": start, "on_touch_move": move, "on_touch_end": end}


@component
def Modal(*children: Any, visible: bool = True, animation_type: str = "none", transparent: bool = False,
          on_request_close: Optional[Callable[[], Any]] = None, backdrop_color: Any = "rgba(0,0,0,0.5)",
          duration: float = 250, style: Any = None, **props: Any):
    """Full-screen layer above the whole app. `animation_type`: none | fade | slide. Android back fires
    `on_request_close`. With `transparent` the layer has no backdrop colour."""
    from .animated import Animated, use_animated_value
    from .env import use_window_dimensions
    animated = animation_type in ("fade", "slide")
    mounted, set_mounted = use_state(bool(visible))
    p = use_animated_value(1.0 if visible else 0.0)
    h = use_window_dimensions()["height"]
    from .hooks import use_effect

    first = use_ref(True)

    def run() -> None:
        if first.current:
            first.current = False
            return
        if not animated:  # keep state in sync so a later switch to fade/slide does not flash a stale layer
            set_mounted(bool(visible))
            p.set_value(1.0 if visible else 0.0)
            return
        if visible:
            set_mounted(True)
            Animated.timing(p, 1.0, duration=duration).start()
        else:
            # Unmount only when the fade-out ran to the end; an interrupted one means visible came back.
            Animated.timing(p, 0.0, duration=duration).start(
                lambda r: set_mounted(False) if r.get("finished") else None)

    use_effect(run, [bool(visible), animated])
    slide_y = use_memo(lambda: p.interpolate([0, 1], [h, 0]), [h])  # one node per height, not per render
    show = (mounted or visible) if animated else bool(visible)
    if not show:
        return None
    fill = {"flex": 1, "background_color": "transparent" if transparent else backdrop_color}
    if animation_type == "fade":
        fill["opacity"] = p
    box: Dict[str, Any] = {"flex": 1}
    if animation_type == "slide":
        box["transform"] = [{"translate_y": slide_y}]
        fill = {"flex": 1, "background_color": "transparent" if transparent else backdrop_color}
    inner = View(*children, style=[box, style], **props)
    return _Modal(View(inner, style=fill), on_request_close=on_request_close,
                  style={"position": "absolute", "left": 0, "top": 0, "right": 0, "bottom": 0})
