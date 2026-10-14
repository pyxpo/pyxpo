"""Platform-native controls (UISwitch / android.widget.Switch, UISlider / SeekBar, ...).

Each control renders as one native view with the platform look by default. Colors, sizes and the box style
(`style`) customise it; `native=False` on the public components falls back to the fully custom-drawn version.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .element import _host
from .style import parse_color

_Switch = _host("NativeSwitch")
_CheckBox = _host("NativeCheckBox")
_Radio = _host("NativeRadio")
_Slider = _host("NativeSlider")
_Progress = _host("NativeProgress")
_Spinner = _host("NativeSpinner")


_SELF = {"align_self": "flex-start"}  # intrinsic size: a stretched native switch would draw at the far edge


def _c(v: Any) -> Optional[int]:
    return None if v is None else parse_color(v)


def _pair(v: Any, on: Any = None, off: Any = None) -> Dict[str, Any]:
    """`v` is one color or {"on": ..., "off": ...}."""
    if isinstance(v, dict):
        return {"on": _c(v.get("on", on)), "off": _c(v.get("off", off))}
    return {"on": _c(v if v is not None else on), "off": _c(off)}


def _clean(props: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in props.items() if v is not None}


def native_switch(value: bool, on_value_change: Any, disabled: bool, track_color: Any, thumb_color: Any,
                  style: Any, key: Any, extra: Dict[str, Any]):
    track = _pair(track_color)
    thumb = _pair(thumb_color)
    return _Switch(key=key, style=[_SELF, style], **_clean({
        "value": bool(value), "disabled": bool(disabled) or None,
        "track_on": track["on"], "track_off": track["off"], "thumb_on": thumb["on"], "thumb_off": thumb["off"],
        "on_value_change": on_value_change, **extra}))


def native_checkbox(value: bool, on_value_change: Any, disabled: bool, color: Any, unchecked_color: Any,
                    style: Any, key: Any, extra: Dict[str, Any]):
    return _CheckBox(key=key, style=[_SELF, style], **_clean({
        "value": bool(value), "disabled": bool(disabled) or None, "color": _c(color),
        "unchecked_color": _c(unchecked_color), "on_value_change": on_value_change, **extra}))


def native_radio(selected: bool, on_press: Any, disabled: bool, color: Any, unchecked_color: Any, style: Any,
                 key: Any, extra: Dict[str, Any]):
    return _Radio(key=key, style=[_SELF, style], **_clean({
        "value": bool(selected), "disabled": bool(disabled) or None, "color": _c(color),
        "unchecked_color": _c(unchecked_color), "on_press": on_press, **extra}))


def native_slider(value: float, minimum: float, maximum: float, step: float, on_value_change: Any,
                  on_sliding_complete: Any, disabled: bool, min_track_color: Any, max_track_color: Any,
                  thumb_color: Any, style: Any, key: Any, extra: Dict[str, Any]):
    return _Slider(key=key, style=style, **_clean({
        "value": float(value), "minimum": float(minimum), "maximum": float(maximum), "step": float(step),
        "disabled": bool(disabled) or None, "min_track_color": _c(min_track_color),
        "max_track_color": _c(max_track_color), "thumb_color": _c(thumb_color),
        "on_value_change": on_value_change, "on_sliding_complete": on_sliding_complete, **extra}))


def native_progress(value: Optional[float], color: Any, track_color: Any, style: Any, key: Any,
                    extra: Dict[str, Any]):
    return _Progress(key=key, style=style, **_clean({
        "value": None if value is None else max(0.0, min(1.0, float(value))),
        "indeterminate": True if value is None else None, "color": _c(color), "track_color": _c(track_color),
        **extra}))


def native_spinner(size: Any, color: Any, animating: bool, style: Any, key: Any, extra: Dict[str, Any]):
    dp = {"small": 20, "large": 36}.get(size, size) if isinstance(size, (int, float, str)) else 20
    return _Spinner(key=key, style=[_SELF, {"width": dp, "height": dp}, style], **_clean({
        "color": _c(color), "animating": None if animating else False, **extra}))
