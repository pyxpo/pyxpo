from __future__ import annotations

from typing import Any

from ..component import component
from ..hooks import _use_keyboard_state
from ..style import flatten
from .view import View


@component
def KeyboardAvoidingView(*children: Any, behavior: Any = None, keyboard_vertical_offset: float = 0.0,
                         content_container_style: Any = None, enabled: bool = True, style: Any = None, **props: Any):
    """Moves its content above the keyboard. `behavior`: "padding" | "height" | "position"; without one the view
    is a plain View (as in RN)."""
    kb = _use_keyboard_state()
    lift = max(0.0, kb["height"] - keyboard_vertical_offset) if (enabled and behavior) else 0.0
    st = flatten(style)
    if behavior == "position":
        inner = View(*children, style=[content_container_style, {"position": "relative", "bottom": lift}])
        return View(inner, style=st, **props)
    if lift:
        extra = st.get("padding_bottom", st.get("padding_vertical", st.get("padding", 0)))
        st = {**st, "padding_bottom": lift + (extra if isinstance(extra, (int, float)) else 0)}
    return View(*children, style=st, **props)
