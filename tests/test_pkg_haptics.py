"""pyxpo-haptics: expo-haptics API, value checks, desktop no-op and the native calls."""
import asyncio

import pytest

from pyxpo.module_testing import FakeBridge

import pyxpo_haptics as Haptics


def run(coro):
    return asyncio.run(coro)


def test_desktop_does_nothing():
    run(Haptics.impactAsync())
    run(Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error))
    run(Haptics.selectionAsync())
    run(Haptics.performAndroidHapticsAsync(Haptics.AndroidHaptics.Confirm))


def test_bad_values():
    for coro in (lambda: Haptics.impact_async("huge"), lambda: Haptics.notification_async("ok"),
                 lambda: Haptics.perform_android_haptics_async("buzz"), lambda: Haptics.impact_async(None)):
        with pytest.raises(ValueError, match="unknown"):
            run(coro())


def test_native_calls():
    with FakeBridge("ios") as fb:
        for m in ("impact", "notification", "selection"):
            fb.on("Haptics", m, lambda *a: None)
        run(Haptics.impact_async())
        run(Haptics.impact_async(Haptics.ImpactFeedbackStyle.Rigid))
        run(Haptics.impact_async("soft"))
        run(Haptics.notification_async())
        run(Haptics.notification_async("warning"))
        run(Haptics.selection_async())
        run(Haptics.perform_android_haptics_async("confirm"))  # iOS: skipped, no native call
        assert fb.calls == [("Haptics", "impact", ("medium",)), ("Haptics", "impact", ("rigid",)),
                            ("Haptics", "impact", ("soft",)), ("Haptics", "notification", ("success",)),
                            ("Haptics", "notification", ("warning",)), ("Haptics", "selection", ())]
    with FakeBridge("android") as fb:
        fb.on("Haptics", "performAndroid", lambda t: None)
        run(Haptics.perform_android_haptics_async(Haptics.AndroidHaptics.Segment_Frequent_Tick))
        assert fb.calls == [("Haptics", "performAndroid", ("segment-frequent-tick",))]


def test_not_linked():
    from pyxpo.module_api import ModuleNotLinkedError
    with FakeBridge("android"):
        with pytest.raises(ModuleNotLinkedError):
            run(Haptics.selection_async())
