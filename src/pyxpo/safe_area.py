"""`react-native-safe-area-context` equivalent: provider, contexts and hooks for the system-bar insets."""
from __future__ import annotations

from typing import Any, Dict, Optional

from .component import component
from .components.safe_area_view import SafeAreaView
from .components.view import View
from .hooks import (SafeAreaFrameContext, SafeAreaInsetsContext, use_safe_area_frame, use_safe_area_insets,
                    useSafeAreaFrame, useSafeAreaInsets)

SafeAreaConsumer = SafeAreaInsetsContext.Consumer


@component
def SafeAreaProvider(*children: Any, initial_metrics: Optional[Dict[str, Any]] = None, style: Any = None, **props: Any):
    """Provides insets and frame to the subtree. Optional: the hooks read the device when no provider is mounted.
    `initial_metrics={"insets": {...}, "frame": {...}}` pins the values (previews, tests)."""
    live_insets, live_frame = use_safe_area_insets(), use_safe_area_frame()
    m = initial_metrics or {}
    insets = dict({"top": 0, "right": 0, "bottom": 0, "left": 0}, **m["insets"]) if m.get("insets") else live_insets
    frame = dict({"x": 0, "y": 0, "width": 0, "height": 0}, **m["frame"]) if m.get("frame") else live_frame
    return SafeAreaInsetsContext.Provider(
        SafeAreaFrameContext.Provider(View(*children, style=[{"flex": 1}, style], **props), value=frame), value=insets)


__all__ = ["SafeAreaConsumer", "SafeAreaFrameContext", "SafeAreaInsetsContext", "SafeAreaProvider", "SafeAreaView",
           "use_safe_area_frame", "use_safe_area_insets", "useSafeAreaFrame", "useSafeAreaInsets"]
