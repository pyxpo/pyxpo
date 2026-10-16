"""Haptic (touch) feedback: the expo-haptics API.

    import pyxpo_haptics as Haptics

    await Haptics.impact_async(Haptics.ImpactFeedbackStyle.Medium)            # or Haptics.impactAsync
    await Haptics.notification_async(Haptics.NotificationFeedbackType.Success)
    await Haptics.selection_async()
    await Haptics.perform_android_haptics_async(Haptics.AndroidHaptics.Confirm)  # Android only

iOS uses the system feedback generators (UIImpactFeedbackGenerator, UINotificationFeedbackGenerator,
UISelectionFeedbackGenerator). The Simulator has no Taptic Engine, so nothing is felt there. Android
plays short vibration patterns (needs the VIBRATE permission, added by this module);
`perform_android_haptics_async` uses the system haptic constants instead, which follow the user's
"touch feedback" setting. On the desktop every call does nothing.
"""
from __future__ import annotations

from enum import Enum
from typing import Type, TypeVar, Union

from pyxpo.module_api import call, platform, require_linked

__version__ = "0.1.0a1"


class ImpactFeedbackStyle(str, Enum):
    """Mass of the colliding objects for `impact_async`."""
    Light = "light"
    Medium = "medium"
    Heavy = "heavy"
    Rigid = "rigid"
    Soft = "soft"


class NotificationFeedbackType(str, Enum):
    """Outcome a `notification_async` feedback stands for."""
    Success = "success"
    Warning = "warning"
    Error = "error"


class AndroidHaptics(str, Enum):
    """System haptic constants for `perform_android_haptics_async`. Types the device's Android version lacks
    fall back to a close older one (noted per value)."""
    Confirm = "confirm"                        # Android 11+, else virtual-key
    Reject = "reject"                          # Android 11+, else long-press
    Gesture_Start = "gesture-start"            # Android 11+, else virtual-key
    Gesture_End = "gesture-end"                # Android 11+, else virtual-key
    Toggle_On = "toggle-on"                    # Android 14+, else virtual-key
    Toggle_Off = "toggle-off"                  # Android 14+, else virtual-key
    Clock_Tick = "clock-tick"
    Context_Click = "context-click"
    Drag_Start = "drag-start"                  # Android 14+, else long-press
    Keyboard_Tap = "keyboard-tap"
    Keyboard_Press = "keyboard-press"          # Android 8.1+, else keyboard-tap
    Keyboard_Release = "keyboard-release"      # Android 8.1+, nothing before
    Long_Press = "long-press"
    Virtual_Key = "virtual-key"
    Virtual_Key_Release = "virtual-key-release"  # Android 8.1+, nothing before
    No_Haptics = "no-haptics"                  # Android 14+, nothing before
    Segment_Tick = "segment-tick"              # Android 14+, else clock-tick
    Segment_Frequent_Tick = "segment-frequent-tick"  # Android 14+, else clock-tick
    Text_Handle_Move = "text-handle-move"      # Android 8.1+, else clock-tick


E = TypeVar("E", bound=Enum)


def _value(kind: Type[E], value: Union[E, str], what: str) -> str:
    try:
        return kind(value).value
    except ValueError:
        raise ValueError("unknown %s %r (use one of: %s)" % (what, value, ", ".join(m.value for m in kind))) from None


def _native() -> bool:
    if platform() == "desktop":
        return False
    require_linked("Haptics", "haptics", package="pyxpo-haptics")
    return True


async def impact_async(style: Union[ImpactFeedbackStyle, str] = ImpactFeedbackStyle.Medium) -> None:
    """A collision between objects: `Light`, `Medium` (default), `Heavy`, `Rigid` or `Soft`."""
    s = _value(ImpactFeedbackStyle, style, "ImpactFeedbackStyle")
    if _native():
        await call("Haptics", "impact", s, reply=True)


async def notification_async(type: Union[NotificationFeedbackType, str] = NotificationFeedbackType.Success) -> None:
    """The outcome of a task: `Success` (default), `Warning` or `Error`."""
    t = _value(NotificationFeedbackType, type, "NotificationFeedbackType")
    if _native():
        await call("Haptics", "notification", t, reply=True)


async def selection_async() -> None:
    """A selection change, for example a picker wheel moving to the next value."""
    if _native():
        await call("Haptics", "selection", reply=True)


async def perform_android_haptics_async(type: Union[AndroidHaptics, str]) -> None:
    """Plays a system haptic constant on Android (follows the user's touch-feedback setting, needs no
    permission). Does nothing on iOS and the desktop."""
    t = _value(AndroidHaptics, type, "AndroidHaptics")
    if platform() == "android" and _native():
        await call("Haptics", "performAndroid", t, reply=True)


impactAsync = impact_async
notificationAsync = notification_async
selectionAsync = selection_async
performAndroidHapticsAsync = perform_android_haptics_async

__all__ = [
    "ImpactFeedbackStyle", "NotificationFeedbackType", "AndroidHaptics", "impact_async", "notification_async",
    "selection_async", "perform_android_haptics_async", "impactAsync", "notificationAsync", "selectionAsync",
    "performAndroidHapticsAsync",
]

