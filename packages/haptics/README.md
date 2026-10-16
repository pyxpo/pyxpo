# pyxpo-haptics

Haptic (touch) feedback for pyxpo apps. The API follows expo-haptics.

This is an optional [pyxpo](https://github.com/pyxpo/pyxpo) native module. Apps that do not
list it carry none of its code, permissions or dependencies.

## Install

```bash
pip install pyxpo-haptics
```

Then link it into your app in `pyproject.toml`:

```toml
[tool.pyxpo]
modules = ["haptics"]
```

and rebuild (`pyxpo run ios`, `pyxpo build android`, ...).

## Use

```python
import pyxpo_haptics as Haptics

await Haptics.impact_async(Haptics.ImpactFeedbackStyle.Heavy)          # or Haptics.impactAsync
await Haptics.notification_async(Haptics.NotificationFeedbackType.Error)
await Haptics.selection_async()
await Haptics.perform_android_haptics_async(Haptics.AndroidHaptics.Confirm)  # Android only
```

- `impact_async(style)`: `Light`, `Medium` (default), `Heavy`, `Rigid`, `Soft`.
- `notification_async(type)`: `Success` (default), `Warning`, `Error`.
- `selection_async()`: a selection change, for example a picker moving to the next value.
- `perform_android_haptics_async(type)`: a system haptic constant (`AndroidHaptics.Confirm`, `Reject`,
  `Long_Press`, `Clock_Tick`, ...). It follows the user's touch-feedback setting and does nothing on iOS.
  Types newer than the device's Android version fall back to a close older one.

Enum members and their string values (`"heavy"`, `"error"`, ...) are both accepted.

- iOS uses the UIKit feedback generators. The Simulator has no Taptic Engine, so nothing is felt there.
- Android plays short vibration patterns and needs the `VIBRATE` permission, which this module adds.
  The patterns are pyxpo's own and are not tuned to match Expo's.
- On the desktop every call does nothing.

## What is in the package

- `pyxpo_haptics/__init__.py`: the Python API.
- `pyxpo_haptics/pyxpo-module.json`: autolink metadata.
- `pyxpo_haptics/ios/`: Swift sources compiled into the iOS app.
- `pyxpo_haptics/android/src/main/`: Kotlin sources and the manifest merged into the Android app.
