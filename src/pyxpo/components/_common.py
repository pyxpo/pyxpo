from __future__ import annotations

from typing import Any, Dict

ACCESSIBILITY = ("accessible", "accessibility_label", "accessibility_hint", "accessibility_role",
                 "accessibility_state", "accessibility_value")
ACCENT = "#2196F3"  # default tint of the platform controls (RN's Switch/ActivityIndicator/Slider blue)


def accessibility(props: Dict[str, Any]) -> Dict[str, Any]:
    return {k: props[k] for k in ACCESSIBILITY if k in props}


def passthrough(props: Dict[str, Any]) -> Dict[str, Any]:
    """Props forwarded to the native control as-is: event handlers, ids, accessibility."""
    return {k: v for k, v in props.items() if k.startswith("on_") or k in ("test_id", "native_id") or k in ACCESSIBILITY}
