from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from ..component import component
from . import _native
from ._common import ACCENT, passthrough


@component
def Switch(value: bool = False, on_value_change: Optional[Callable[[bool], Any]] = None, disabled: bool = False,
           track_color: Any = None, thumb_color: Any = None, style: Any = None, key: Any = None, **props: Any):
    """Platform switch. `trackColor` / `thumbColor` take one colour or RN's `{False: off, True: on}`."""
    track = _native.pair(track_color if track_color is not None else {True: ACCENT})
    thumb = _native.pair(thumb_color)
    return _native.Switch(key=key, style=[_native.SELF, style], **_native.clean({
        "value": bool(value), "disabled": True if disabled else None,
        "track_on": track["on"], "track_off": track["off"], "thumb_on": thumb["on"], "thumb_off": thumb["off"],
        "on_value_change": on_value_change, **passthrough(props)}))
