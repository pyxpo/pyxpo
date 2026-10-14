"""TouchableOpacity, TouchableHighlight, TouchableWithoutFeedback, TouchableNativeFeedback: the classic RN
touchables, built on the same press events as Pressable."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from ..component import component
from ..hooks import use_state
from ..style import flatten
from ._common import accessibility
from .view import View

_FORWARD = ("test_id", "native_id", "on_layout", "hit_slop", "delay_long_press", "pointer_events")


def _touchable(children: Any, style: Dict[str, Any], disabled: bool, on_press: Any, on_long_press: Any,
               on_press_in: Any, on_press_out: Any, set_pressed: Callable[[bool], Any],
               props: Dict[str, Any]) -> Any:
    extra: Dict[str, Any] = accessibility(props)
    if disabled:
        extra["accessibility_state"] = {**extra.get("accessibility_state", {}), "disabled": True}
    else:
        if on_press is not None:
            extra["on_press"] = on_press
        if on_long_press is not None:
            extra["on_long_press"] = on_long_press
        extra["on_press_in"] = lambda *a: (set_pressed(True), on_press_in and on_press_in())[0]
        extra["on_press_out"] = lambda *a: (set_pressed(False), on_press_out and on_press_out())[0]
    for k in _FORWARD:
        if k in props:
            extra[k] = props[k]
    return View(*children, style=style, **extra)


@component
def TouchableOpacity(*children: Any, active_opacity: float = 0.2, disabled: bool = False, style: Any = None,
                     on_press: Optional[Callable] = None, on_long_press: Optional[Callable] = None,
                     on_press_in: Optional[Callable] = None, on_press_out: Optional[Callable] = None, **props: Any):
    """Dims to `activeOpacity` (default 0.2) while pressed."""
    pressed, set_pressed = use_state(False)
    st = flatten(style)
    if pressed and not disabled:
        st = {**st, "opacity": st.get("opacity", 1.0) * active_opacity}
    return _touchable(children, st, disabled, on_press, on_long_press, on_press_in, on_press_out, set_pressed, props)


@component
def TouchableHighlight(*children: Any, underlay_color: Any = "black", active_opacity: float = 0.85,
                       disabled: bool = False, style: Any = None, on_press: Optional[Callable] = None,
                       on_long_press: Optional[Callable] = None, on_press_in: Optional[Callable] = None,
                       on_press_out: Optional[Callable] = None, **props: Any):
    """Shows `underlayColor` behind the content and dims the content to `activeOpacity` while pressed."""
    pressed, set_pressed = use_state(False)
    st = flatten(style)
    kids: Any = children
    if pressed and not disabled:
        st = {**st, "background_color": underlay_color}
        kids = [View(*children, style={"opacity": active_opacity})]
    return _touchable(kids, st, disabled, on_press, on_long_press, on_press_in, on_press_out, set_pressed, props)


@component
def TouchableWithoutFeedback(*children: Any, disabled: bool = False, on_press: Optional[Callable] = None,
                             on_long_press: Optional[Callable] = None, on_press_in: Optional[Callable] = None,
                             on_press_out: Optional[Callable] = None, style: Any = None, **props: Any):
    """Handles presses and shows nothing."""
    return _touchable(children, flatten(style), disabled, on_press, on_long_press, on_press_in, on_press_out,
                      lambda p: None, props)


@component
def TouchableNativeFeedback(*children: Any, background: Any = None, disabled: bool = False, style: Any = None,
                            on_press: Optional[Callable] = None, on_long_press: Optional[Callable] = None,
                            on_press_in: Optional[Callable] = None, on_press_out: Optional[Callable] = None,
                            **props: Any):
    """Android ripple feedback. `background` is `{"color", "borderless"}` (see TouchableNativeFeedback.Ripple)."""
    if background:
        props["android_ripple"] = background
    return _touchable(children, flatten(style), disabled, on_press, on_long_press, on_press_in, on_press_out,
                      lambda p: None, props)


def _ripple(color: Any, borderless: bool = False, radius: Optional[float] = None) -> Dict[str, Any]:
    return {"color": color, "borderless": borderless, **({"radius": radius} if radius else {})}


TouchableNativeFeedback.Ripple = _ripple
