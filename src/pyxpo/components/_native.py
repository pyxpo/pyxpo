"""Native control hosts (UISwitch / android.widget.Switch, SeekBar, ProgressBar, ...) shared by the RN
components Switch, Slider and ActivityIndicator."""
from __future__ import annotations

from typing import Any, Dict, Optional

from ..element import _host
from ..style import processColor

Switch = _host("NativeSwitch")
Slider = _host("NativeSlider")
Spinner = _host("NativeSpinner")

SELF = {"align_self": "flex-start"}  # intrinsic size: a stretched native switch would draw at the far edge


def color(v: Any) -> Optional[int]:
    return None if v is None else processColor(v)


def pair(v: Any) -> Dict[str, Any]:
    """RN `{false: c, true: c}` (or a single color for the on state)."""
    if isinstance(v, dict):
        return {"on": color(v.get(True, v.get("true", v.get("on")))), "off": color(v.get(False, v.get("false", v.get("off"))))}
    return {"on": color(v), "off": None}


def clean(props: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in props.items() if v is not None}
