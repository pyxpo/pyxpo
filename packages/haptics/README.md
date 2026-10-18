# pyxpo-haptics

Touch feedback for [pyxpo](https://github.com/pyxpo/pyxpo) apps, written in Python: impact taps, success and error
buzzes, selection ticks, and the Android system haptic constants. The names follow
[expo-haptics](https://docs.expo.dev/versions/latest/sdk/haptics/), in Python style.

<p align="center">
  <img src="https://raw.githubusercontent.com/pyxpo/pyxpo/main/packages/haptics/docs/images/hero.png" width="820" alt="The haptics module on Android and iOS: impact, notification and selection buttons, and the Android system haptics">
</p>

```python
import pyxpo_haptics as Haptics

await Haptics.impact_async(Haptics.ImpactFeedbackStyle.Heavy)
await Haptics.notification_async(Haptics.NotificationFeedbackType.Success)
await Haptics.selection_async()
```

## Features

- **Three kinds of feedback:** `impact_async` (five weights), `notification_async` (success, warning, error) and
  `selection_async` (a light tick).
- **Android system haptics:** `perform_android_haptics_async` plays the system constants (`Confirm`, `Reject`,
  `Long_Press`, `Clock_Tick`, ...). They follow the user's touch-feedback setting and need no permission.
- **Enums or strings:** `Haptics.ImpactFeedbackStyle.Heavy` and `"heavy"` both work. A wrong value raises a
  `ValueError` that lists the valid ones.
- **Safe everywhere:** on the desktop and the web every call returns without doing anything, so shared code does
  not need a guard.
- **Small:** one permission (`VIBRATE`, added by the module), no dependencies, no prompt.
- **Typed:** ships `py.typed`. Every name also has its expo spelling (`Haptics.impactAsync`).

## Contents

| If you are... | Start here |
| --- | --- |
| Adding a tap to a button | [Quick start](#quick-start) |
| Choosing between impact, notification and selection | [Feedback kinds](#feedback-kinds) |
| Using the Android system constants | [Android system haptics](#android-system-haptics) |
| Worried about devices without a motor | [Platform support](#platform-support) · [Troubleshooting](#troubleshooting) |
| Looking for exact signatures | [API reference](#api-reference) · [Errors](#errors) |
| Seeing it in a real app | [Recipe: feedback on a form](#recipe-feedback-on-a-form) |
| Stuck | [Testing](#testing) · [Troubleshooting](#troubleshooting) · [FAQ](#faq) |

## Platform support

| Target | What works |
| --- | --- |
| Android, API 24+ | All four functions. Impact and notification play short vibration patterns, so the phone needs a vibration motor. `perform_android_haptics_async` uses the system constants. |
| iOS 15+ | `impact_async`, `notification_async`, `selection_async` through the UIKit feedback generators. `perform_android_haptics_async` does nothing. |
| Web page and desktop window (`pyxpo run web` / `pyxpo run desktop`) | Every call does nothing and does not raise. |

The iOS Simulator has no Taptic Engine, so nothing is felt there. See [what the screenshots show](#what-the-screenshots-show).

Requires Python 3.9+ and `pyxpo>=0.1.0a2`.

## Install

```sh
pip install pyxpo-haptics
```

Add the module to your app's `pyproject.toml`:

```toml
[tool.pyxpo]
modules = ["haptics"]
```

The module has native code, so rebuild the app after adding it (`pyxpo run android` or `pyxpo run ios`). On Android
the module adds the `VIBRATE` permission to the manifest for you. It is a normal permission, so there is no prompt.

## Quick start

```python
import pyxpo_haptics as Haptics
from pyxpo import Pressable, Text, View, component, use_state


@component
def Counter():
    count, set_count = use_state(0)

    async def tap():
        await Haptics.impact_async(Haptics.ImpactFeedbackStyle.Light)
        set_count(count + 1)

    return View(
        Text("Taps: %d" % count),
        Pressable(Text("Tap"), on_press=tap),
    )
```

> **Tip:** call the haptic in the press handler, before or together with the state change, so the buzz lands at the
> same moment as the touch. Do not wait on it in a loop. Each call is a short round trip to the native side.

## Feedback kinds

```python
await Haptics.impact_async(Haptics.ImpactFeedbackStyle.Medium)          # default is Medium
await Haptics.notification_async(Haptics.NotificationFeedbackType.Error)  # default is Success
await Haptics.selection_async()
```

| Function | Values | Use it for |
| --- | --- | --- |
| `impact_async(style)` | `Light`, `Medium` (default), `Heavy`, `Rigid`, `Soft` | A tap or a collision. The style is the mass of the colliding objects: `Heavy` is a thud, `Rigid` a sharp click, `Soft` a cushioned one. |
| `notification_async(type)` | `Success` (default), `Warning`, `Error` | The outcome of a task: a saved form, a risky action, a failed login. |
| `selection_async()` | none | A value changing under the finger: a picker wheel, a slider step, a segmented control. |

On iOS these map to `UIImpactFeedbackGenerator`, `UINotificationFeedbackGenerator` and `UISelectionFeedbackGenerator`.
On Android they are short vibration patterns that pyxpo chose itself, so they feel close to iOS but are not tuned to
match Expo's.

Enum members and their string values are both accepted:

```python
await Haptics.impact_async("heavy")
await Haptics.impact_async(Haptics.ImpactFeedbackStyle("heavy"))
```

## Android system haptics

```python
await Haptics.perform_android_haptics_async(Haptics.AndroidHaptics.Confirm)
await Haptics.perform_android_haptics_async("long-press")
```

This plays a constant of the Android view system. It follows the user's "touch feedback" setting and needs no
permission. On iOS and the desktop it does nothing. A constant that your device's Android version does not have
falls back to a close older one:

| `AndroidHaptics` member | Needs | Falls back to |
| --- | --- | --- |
| `Confirm`, `Gesture_Start`, `Gesture_End` | Android 11 | `Virtual_Key` |
| `Reject` | Android 11 | `Long_Press` |
| `Toggle_On`, `Toggle_Off` | Android 14 | `Virtual_Key` |
| `Drag_Start` | Android 14 | `Long_Press` |
| `Keyboard_Press`, `Text_Handle_Move` | Android 8.1 | `Keyboard_Tap`, `Clock_Tick` |
| `Keyboard_Release`, `Virtual_Key_Release` | Android 8.1 | nothing |
| `Segment_Tick`, `Segment_Frequent_Tick` | Android 14 | `Clock_Tick` |
| `No_Haptics` | Android 14 | nothing |
| `Clock_Tick`, `Context_Click`, `Keyboard_Tap`, `Long_Press`, `Virtual_Key` | any | |

<p align="center">
  <img src="https://raw.githubusercontent.com/pyxpo/pyxpo/main/packages/haptics/docs/images/android.png" width="420" alt="The Android system haptics section of the demo screen">
</p>

## What the screenshots show

A haptic is a feeling, so a screenshot can only show the controls and the confirmation text, not the buzz. The demo
screen shows every function as a button and prints "Tap a button to feel it". The iOS Simulator has no Taptic Engine
and the Android emulator has no vibration motor, so the screenshots are of the screen, not of the feedback. Test the
feeling on a real phone.

## Errors

| Error | When | What to do |
| --- | --- | --- |
| `ValueError: unknown ImpactFeedbackStyle 'x' (use one of: ...)` | A style, type or Android constant that does not exist. | Use an enum member or one of the listed strings. |
| `ModuleNotLinkedError` (from `pyxpo.module_api`) | The app was built without `"haptics"` in `modules`. | Add it and rebuild. |

There is no `NotSupportedError`. A platform that cannot play a haptic returns without doing anything.

## Config

There are no module options and no config plugin. The only setup is the `modules` entry. The Android `VIBRATE`
permission is merged into the manifest by the module itself.

## Web and desktop

`pyxpo run web` and `pyxpo run desktop` accept every call and return at once. Value checks still run, so a typo in a
style name raises `ValueError` on the desktop too.

## Recipe: feedback on a form

Tick when the user changes a choice, a success buzz on save and an error buzz on a failed save.

```python
import pyxpo_haptics as Haptics
from pyxpo import Pressable, Text, View, component, use_state


async def save_to_server(plan: str) -> None:
    ...


@component
def PlanForm():
    plan, set_plan = use_state("free")
    status, set_status = use_state("")

    async def choose(name):
        await Haptics.selection_async()
        set_plan(name)

    async def save():
        try:
            await save_to_server(plan)
        except Exception:
            await Haptics.notification_async(Haptics.NotificationFeedbackType.Error)
            set_status("Could not save")
        else:
            await Haptics.notification_async(Haptics.NotificationFeedbackType.Success)
            set_status("Saved")

    return View(
        Pressable(Text("Free"), on_press=lambda: choose("free")),
        Pressable(Text("Pro"), on_press=lambda: choose("pro")),
        Pressable(Text("Save"), on_press=save),
        Text(status),
    )
```

## Production checklist

- [ ] Haptics are a nicety, not the only signal. An action also shows text or a color change.
- [ ] A heavy feedback is kept for rare events. Many buzzes in a row tire the user.
- [ ] You tested the feeling on a real phone, not only the simulator.
- [ ] Any Android system constant you use has a fallback you are happy with on older Android versions.
- [ ] The user's "touch feedback" and silent settings are respected. The system constants do this for you.

## Testing

Unit tests run on the desktop host, where every call does nothing. To check that your code asks for the right
feedback, replace the function with a fake:

```python
import pyxpo_haptics as Haptics


def test_save_buzzes_success(monkeypatch):
    calls = []

    async def fake(type=Haptics.NotificationFeedbackType.Success):
        calls.append(type)

    monkeypatch.setattr(Haptics, "notification_async", fake)
    # run the code under test, then:
    # assert calls == [Haptics.NotificationFeedbackType.Success]
```

To test the value checks, call the real function with a wrong value and expect `ValueError`.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Nothing is felt on the iOS Simulator | It has no Taptic Engine. Use a real iPhone. |
| Nothing is felt on the Android emulator | It has no vibration motor. Use a real phone. |
| Nothing is felt on an iPhone | Settings > Sounds and Haptics > System Haptics is off, or Low Power Mode is on. |
| Nothing is felt on Android | The phone is silent with vibration off, or "Touch feedback" is off in Settings. |
| `perform_android_haptics_async` does nothing on a phone | It is Android only. On iOS use `impact_async`. |
| An Android constant feels like a plain tap | The device's Android is older than the constant needs, so a fallback played (see the table above). |
| `ValueError: unknown AndroidHaptics` | The name is not a member. Use the string `"long-press"` or the member `Long_Press`. |
| `ModuleNotLinkedError` | Add `"haptics"` to `modules` and rebuild. |

## FAQ

**Does it need a permission prompt?** No. `VIBRATE` is a normal permission and is granted at install.

**Will it work on the web?** The calls succeed and do nothing. Browsers have no general haptics API that pyxpo uses.

**Can I make my own vibration pattern?** Not with this module. It plays the system generators on iOS and fixed
patterns on Android.

**Why are the Android patterns different from Expo's?** They are pyxpo's own, written to suggest the same feeling,
and they are not claimed to be identical.

**Is `impactAsync` the same as `impact_async`?** Yes. Every function has both spellings.

## API reference

### Functions

| Function (expo name) | Platforms | Returns |
| --- | --- | --- |
| `impact_async(style=Medium)` (`impactAsync`) | iOS, Android | `None` |
| `notification_async(type=Success)` (`notificationAsync`) | iOS, Android | `None` |
| `selection_async()` (`selectionAsync`) | iOS, Android | `None` |
| `perform_android_haptics_async(type)` (`performAndroidHapticsAsync`) | Android | `None` |

### Types

| Name | Members |
| --- | --- |
| `ImpactFeedbackStyle` | `Light`, `Medium`, `Heavy`, `Rigid`, `Soft` |
| `NotificationFeedbackType` | `Success`, `Warning`, `Error` |
| `AndroidHaptics` | `Confirm`, `Reject`, `Gesture_Start`, `Gesture_End`, `Toggle_On`, `Toggle_Off`, `Clock_Tick`, `Context_Click`, `Drag_Start`, `Keyboard_Tap`, `Keyboard_Press`, `Keyboard_Release`, `Long_Press`, `Virtual_Key`, `Virtual_Key_Release`, `No_Haptics`, `Segment_Tick`, `Segment_Frequent_Tick`, `Text_Handle_Move` |

All three are `str` enums, so `"heavy"` equals `ImpactFeedbackStyle.Heavy`.

## License

MIT
