from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from ..component import component
from ..hooks import use_state
from ..style import flatten
from ._common import accessibility
from .view import View


def _text_of(els: Any) -> str:
    """Concatenated text of the host Text elements under els (what a screen reader should read for a button)."""
    parts = []
    for e in els:
        if getattr(e, "type", None) == "Text" and isinstance(e.props.get("text"), str):
            parts.append(e.props["text"])
        else:
            parts.append(_text_of(getattr(e, "children", None) or ()))
    return " ".join(p for p in parts if p)


class PressableState:
    """What `Pressable` passes to `style(...)` and to function children: `state.pressed` (also `state["pressed"]`
    and plain truthiness)."""
    __slots__ = ("pressed",)

    def __init__(self, pressed: bool) -> None:
        self.pressed = pressed

    def __bool__(self) -> bool:
        return self.pressed

    def __getitem__(self, k: str) -> bool:
        if k == "pressed":
            return self.pressed
        raise KeyError(k)


_PRESSED, _IDLE = PressableState(True), PressableState(False)

_FORWARD = ("test_id", "native_id", "on_layout", "hit_slop", "android_ripple", "delay_long_press", "pointer_events",
            "on_touch_start", "on_touch_move", "on_touch_end", "href")


@component
def Pressable(*children: Any, on_press: Optional[Callable[..., Any]] = None,
              on_long_press: Optional[Callable[..., Any]] = None, on_press_in: Optional[Callable[..., Any]] = None,
              on_press_out: Optional[Callable[..., Any]] = None, disabled: bool = False, style: Any = None,
              **props: Any):
    """Touchable view. `style` may be a function of the press state; so may the single child.

    Props: onPress, onPressIn, onPressOut, onLongPress, delayLongPress (ms, default 500), disabled, hitSlop,
    android_ripple ({"color", "borderless", "radius"}), testID, accessibility*. A disabled Pressable fires nothing.
    """
    pressed, set_pressed = use_state(False)
    state = _PRESSED if pressed else _IDLE
    st = flatten(style(state) if callable(style) else style)
    render = props.pop("children", None)  # function child: Pressable(lambda state: ...)
    kids: Any = [render(state)] if callable(render) else list(children)
    extra: Dict[str, Any] = accessibility(props)
    if "accessibility_label" not in extra and extra.get("accessible", True) and (
            on_press is not None or on_long_press is not None or "accessibility_role" in extra):
        label = _text_of(kids)
        if label:
            extra["accessibility_label"] = label
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
    return View(*kids, style=st, **extra)
