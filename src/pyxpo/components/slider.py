from __future__ import annotations

from typing import Any, Callable, Optional

from ..component import component
from . import _native
from ._common import ACCENT, passthrough


@component
def Slider(value: float = 0.0, minimum_value: float = 0.0, maximum_value: float = 1.0, step: float = 0.0,
           on_value_change: Optional[Callable[[float], Any]] = None,
           on_sliding_complete: Optional[Callable[[float], Any]] = None, disabled: bool = False,
           minimum_track_tint_color: Any = None, maximum_track_tint_color: Any = None,
           thumb_tint_color: Any = None, style: Any = None, key: Any = None, **props: Any):
    """Platform slider (`@react-native-community/slider` API). Controlled: update `value` in `onValueChange`."""
    return _native.Slider(key=key, style=style, **_native.clean({
        "value": float(value), "minimum": float(minimum_value), "maximum": float(maximum_value), "step": float(step),
        "disabled": True if disabled else None,
        "min_track_color": _native.color(minimum_track_tint_color or ACCENT),
        "max_track_color": _native.color(maximum_track_tint_color),
        "thumb_color": _native.color(thumb_tint_color or ACCENT),
        "on_value_change": on_value_change, "on_sliding_complete": on_sliding_complete, **passthrough(props)}))
