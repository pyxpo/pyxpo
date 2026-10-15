from __future__ import annotations

from typing import Any

from ..component import component
from . import _native
from ._common import ACCENT, passthrough


@component
def ActivityIndicator(animating: bool = True, size: Any = "small", color: Any = None, style: Any = None,
                      hides_when_stopped: bool = True, key: Any = None, **props: Any):
    """Platform spinner. `size`: "small" | "large" | number of dp."""
    dp = {"small": 20, "large": 36}.get(size, size) if isinstance(size, (int, float, str)) else 20
    if not animating and hides_when_stopped:
        style = [style, {"opacity": 0}]
    return _native.Spinner(key=key, style=[{"width": dp, "height": dp}, style], **_native.clean({
        "color": _native.color(color or ACCENT), "animating": None if animating else False, **passthrough(props)}))
