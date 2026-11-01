"""Animated: native-driven animations (Value, timing, spring, decay, composition) and Easing."""
from __future__ import annotations

from typing import Any

from ..components.image import Image
from ..components.scroll_view import ScrollView
from ..components.text import Text
from ..components.view import View
from ..hooks import use_effect, use_ref
from . import runtime
from .api import Animated as _Animated
from .easing import Easing
from .nodes import AnimatedNode, Interpolation, Value, ValueXY


class Animated(_Animated):
    View = View
    Text = Text
    Image = Image
    ScrollView = ScrollView


def use_animated_value(initial: float = 0.0) -> Value:
    """A Value that lives as long as the component. Freed natively on unmount."""
    ref = use_ref(None)
    if ref.current is None:
        ref.current = Value(initial)
    v = ref.current

    def cleanup() -> Any:
        return lambda: runtime.delete_node(v)

    use_effect(cleanup, [])
    return v


__all__ = ["Animated", "AnimatedNode", "Easing", "Interpolation", "Value", "ValueXY", "use_animated_value"]
