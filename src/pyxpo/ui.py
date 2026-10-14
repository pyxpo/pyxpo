"""Interactive components built in Python on top of View: Pressable, Switch, Checkbox.

They draw with the box painter and react to the native press_in/press_out/press/long_press events,
so every colour, size and radius is a style the app can override.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .component import component
from .element import Text, View
from .hooks import use_state
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
