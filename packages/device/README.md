# pyxpo-device

Facts about the device a [pyxpo](https://github.com/pyxpo/pyxpo) app runs on, written in Python: brand, model, OS
and version, memory, CPU architectures, phone or tablet, uptime and Android system features. The names follow
[expo-device](https://docs.expo.dev/versions/latest/sdk/device/), in Python style.

<p align="center">
  <img src="https://raw.githubusercontent.com/pyxpo/pyxpo/main/packages/device/docs/images/hero.png" width="820" alt="The device module on Android and iOS: brand, model, OS version, memory and device type">
</p>

```python
import pyxpo_device as Device

print(Device.brand, Device.model_name, Device.os_name, Device.os_version)   # "Google", "sdk_gphone64_arm64", "Android", "15"
if Device.device_type == Device.DeviceType.TABLET:
    ...
uptime_ms = await Device.get_uptime_async()
```

## Features

- **Constants with no bridge call:** brand, model, OS, memory and the rest are read once at startup and are plain
  attributes of the module.
- **Phone, tablet, TV or desktop:** `Device.device_type` is a `DeviceType` enum, worked out from the platform's own
  idiom and the screen size.
- **Runs on the desktop too:** the web page and the desktop window fill the same fields from Python's `platform`
  module, so layout code can run the same everywhere.
- **Android extras:** the runtime memory limit, the list of system features, a feature check
  (`android.hardware.camera`) and whether the app may install other apps.
- **Honest values:** a value a platform does not have is `None`, not a guess. The rooted check is documented as
  easy to fool.
- **No permissions:** nothing here needs a prompt, an entitlement or a manifest entry.
- **Typed:** ships `py.typed`. Every name also has its expo-device spelling (`Device.modelName`,
  `Device.getUptimeAsync`).

## Contents

| If you are... | Start here |
| --- | --- |
| Showing the model in a support screen | [Quick start](#quick-start) → [Constants](#constants) |
| Switching layouts for tablets | [Device type](#device-type) |
| Checking for a camera or other hardware | [Android system features](#android-system-features) |
| Wondering whether it is an emulator | [`is_device`](#is_device-and-emulators) |
| Looking for exact signatures | [API reference](#api-reference) · [Errors](#errors) |
| Seeing it in a real app | [Recipe: a diagnostics line for support](#recipe-a-diagnostics-line-for-support) |
| Stuck | [Testing](#testing) · [Troubleshooting](#troubleshooting) · [FAQ](#faq) |

## Platform support

| Target | What works |
| --- | --- |
| Android, API 24+ | Everything. |
| iOS | Everything except the Android-only values, which are `None` or an empty result. |
| Web page and desktop window (`pyxpo run web` / `pyxpo run desktop`) | Constants from Python's `platform` module, `device_type` is `DESKTOP`, uptime from the monotonic clock. |

Requires Python 3.9+ and `pyxpo>=0.1.0a2`.

## Install

```sh
pip install pyxpo-device
```

Add the module to your app's `pyproject.toml`:

```toml
[tool.pyxpo]
modules = ["device"]
```

The module has native code, so rebuild the app after adding it (`pyxpo run android` or `pyxpo run ios`).

## Quick start

```python
import pyxpo_device as Device
from pyxpo import Text, View, component, use_async


@component
def DeviceInfo():
    uptime = use_async(Device.get_uptime_async, [])     # (loading, value, error)
    hours = (uptime.value or 0) / 3_600_000
    return View(
        Text("%s %s" % (Device.brand or "", Device.model_name or "")),
        Text("%s %s" % (Device.os_name, Device.os_version)),
        Text("Up for %.1f hours" % hours),
        Text("Tablet" if Device.device_type == Device.DeviceType.TABLET else "Phone"),
    )
```

> **Tip:** the constants resolve when you read them, not when the module is imported, because the startup
> environment is not there yet at import time. Read them inside a component or a function. Do not copy them into
> module-level variables at import.

## Constants

Read once at app start. `None` where a platform has no value.

| Python name | expo name | iOS | Android |
| --- | --- | --- | --- |
| `is_device` | `isDevice` | False on the Simulator | False on an emulator (best-effort check) |
| `brand`, `manufacturer` | `brand`, `manufacturer` | `"Apple"` | `Build.BRAND`, `Build.MANUFACTURER` |
| `model_name` | `modelName` | Marketing name for known iPhones, else the identifier | `Build.MODEL` |
| `model_id` | `modelId` | Identifier, for example `"iPhone17,3"` | `None` |
| `design_name`, `product_name` | `designName`, `productName` | `None` | `Build.DEVICE`, `Build.PRODUCT` |
| `device_year_class` | `deviceYearClass` | Release year of known iPhones | `None` |
| `total_memory` | `totalMemory` | Bytes of RAM | Bytes of RAM |
| `supported_cpu_architectures` | `supportedCpuArchitectures` | `["arm64"]` | `Build.SUPPORTED_ABIS` |
| `os_name` | `osName` | `"iOS"` or `"iPadOS"` | `"Android"` |
| `os_version` | `osVersion` | For example `"26.0"` | For example `"15"` |
| `os_build_id`, `os_internal_build_id` | `osBuildId`, `osInternalBuildId` | Kernel OS build | `Build.DISPLAY`, `Build.ID` |
| `os_build_fingerprint`, `platform_api_level` | `osBuildFingerprint`, `platformApiLevel` | `None` | `Build.FINGERPRINT`, the API level |
| `device_name` | `deviceName` | `UIDevice.name` (a generic name on iOS 16+) | The device name setting, else the model |
| `device_type` | `deviceType` | `DeviceType` from the interface idiom | `DeviceType` from TV mode and screen width (600dp and up is a tablet) |

<p align="center">
  <img src="https://raw.githubusercontent.com/pyxpo/pyxpo/main/packages/device/docs/images/constants.png" width="720" alt="Constants on Android and iOS">
</p>

### `is_device` and emulators

`is_device` is `False` on the iOS Simulator and, on a best-effort basis, on the Android emulator. Use it to skip
features that need real hardware (haptics, camera). Do not use it for security.

## Device type

```python
if Device.device_type == Device.DeviceType.TABLET:
    columns = 3
```

| `DeviceType` | Value | Meaning |
| --- | --- | --- |
| `UNKNOWN` | 0 | The platform could not tell. |
| `PHONE` | 1 | A phone. |
| `TABLET` | 2 | A tablet (an iPad, or Android 600dp and wider). |
| `DESKTOP` | 3 | The web page or the desktop window. |
| `TV` | 4 | Android TV mode. |

`await Device.get_device_type_async()` returns the same value as the constant.

## Memory and uptime

```python
total = Device.total_memory                       # bytes of RAM
limit = await Device.get_max_memory_async()       # Android: the runtime limit; elsewhere MAX_SAFE_INTEGER
ms = await Device.get_uptime_async()              # milliseconds since boot, not counting deep sleep
```

`MAX_SAFE_INTEGER` (`2 ** 53 - 1`) is what expo-device returns when memory has no inherent limit, which is the case
on iOS and the desktop.

## Android system features

```python
if await Device.has_platform_feature_async("android.hardware.camera"):
    show_camera_button()
names = await Device.get_platform_features_async()        # every feature the device reports
```

`has_platform_feature_async(feature)` takes a non-empty string and raises `ValueError` otherwise. On iOS and the
desktop it returns `False`, and `get_platform_features_async()` returns `[]`.

`is_side_loading_enabled_async()` tells whether this app may install other apps. It needs the
`REQUEST_INSTALL_PACKAGES` permission on Android 8 and later, and is always `False` on iOS and the desktop.

`is_rooted_experimental_async()` is a best-effort jailbreak or root check. It is easy to fool, so never use it as
a security decision.

## Errors

| Error | When | What to do |
| --- | --- | --- |
| `ValueError` | `has_platform_feature_async` gets an empty or non-string feature. | Pass a feature name such as `"android.hardware.camera"`. |
| `ModuleNotLinkedError` (from `pyxpo.module_api`) | The app was built without `"device"` in `modules`. | Add it and rebuild. The desktop is exempt. |
| `AttributeError` | A name that is not a constant, for example a typo. | Check the [Constants](#constants) table. |

## Config

There are no module options and no config plugin. The only native setup is the `modules` entry.

## Web and desktop

The same names work. Values come from Python's `platform` module (`uname()`), `total_memory` from `sysconf` where
available, `device_type` is `DESKTOP`, brand and model are `None`, and `get_uptime_async()` uses the monotonic
clock. `is_rooted_experimental_async()`, `is_side_loading_enabled_async()` and `has_platform_feature_async()`
return `False`.

## Recipe: a diagnostics line for support

One line the user can paste into a support email.

```python
import pyxpo_application as Application
import pyxpo_device as Device


def diagnostics() -> str:
    gb = (Device.total_memory or 0) / 1024 ** 3
    parts = [
        "%s %s" % (Device.brand or "?", Device.model_name or "?"),
        "%s %s" % (Device.os_name, Device.os_version),
        "%.1f GB" % gb,
        "app %s" % (Application.native_application_version or "dev"),
    ]
    if Device.platform_api_level:
        parts.append("API %s" % Device.platform_api_level)
    if not Device.is_device:
        parts.append("emulator")
    return " | ".join(parts)
```

## Production checklist

- [ ] No decision about security or licensing depends on `is_rooted_experimental_async()` or `is_device`.
- [ ] Layouts do not assume a phone: `DeviceType.TABLET` and `DESKTOP` are handled.
- [ ] Android-only values (`platform_api_level`, `model_id` on iOS) are `None`-checked.
- [ ] A feature that needs hardware checks `has_platform_feature_async` before showing its button.
- [ ] Device names (`device_name`) are not sent to your server without the user knowing.

## Testing

Constants are read through `pyxpo.module_api`. Patch `_all` to control them:

```python
import pyxpo_device as Device


def test_tablet_layout(monkeypatch):
    monkeypatch.setattr(Device, "_all", lambda: {**{k: None for k in Device._FIELDS}, "deviceType": 2})
    assert Device.device_type == Device.DeviceType.TABLET
```

On the desktop test host the values come from Python's `platform` module, and `device_type` is `DESKTOP`.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `brand` and `model_name` are `None` | You are on the desktop or the web page. They only exist on a phone. |
| `model_id` is `None` on Android | It is iOS only. Use `product_name` or `design_name`. |
| `device_year_class` is `None` | Unknown iPhone model, or Android. |
| `get_max_memory_async()` returns a huge number | iOS and the desktop have no runtime limit, so it is `MAX_SAFE_INTEGER`. |
| `is_side_loading_enabled_async()` is always `False` | Add `REQUEST_INSTALL_PACKAGES` to the Android manifest, and note iOS is always `False`. |
| `ModuleNotLinkedError` | Add `"device"` to `[tool.pyxpo] modules` and rebuild. |

## FAQ

**Is `device_name` the user's name?** It is the name in the device settings. On iOS 16 and later Apple returns a
generic name such as "iPhone" unless the app has a special entitlement.

**Does it need any permission?** No.

**Is the tablet check reliable?** On iOS it follows the interface idiom (iPad is a tablet). On Android it follows
TV mode and a 600dp screen width.

**Why `total_memory` and not free memory?** It is the installed RAM. Free memory changes every second and is not
something the system promises to report.

## API reference

### Constants

`is_device`, `brand`, `manufacturer`, `model_name`, `model_id`, `design_name`, `product_name`, `device_year_class`,
`total_memory`, `supported_cpu_architectures`, `os_name`, `os_version`, `os_build_id`, `os_internal_build_id`,
`os_build_fingerprint`, `platform_api_level`, `device_name`, `device_type`. Each has a camelCase twin.

### Functions

| Function (expo name) | Platforms | Returns |
| --- | --- | --- |
| `get_device_type_async()` (`getDeviceTypeAsync`) | all | `DeviceType` |
| `get_uptime_async()` (`getUptimeAsync`) | all | `int` milliseconds |
| `get_max_memory_async()` (`getMaxMemoryAsync`) | all | `int` bytes, `MAX_SAFE_INTEGER` when unlimited |
| `is_rooted_experimental_async()` (`isRootedExperimentalAsync`) | all | `bool` |
| `is_side_loading_enabled_async()` (`isSideLoadingEnabledAsync`) | Android | `bool`, `False` elsewhere |
| `get_platform_features_async()` (`getPlatformFeaturesAsync`) | Android | `list[str]`, `[]` elsewhere |
| `has_platform_feature_async(feature)` (`hasPlatformFeatureAsync`) | Android | `bool`, `False` elsewhere |

### Types

| Name | Description |
| --- | --- |
| `DeviceType` | `IntEnum`: `UNKNOWN`, `PHONE`, `TABLET`, `DESKTOP`, `TV`. |
| `MAX_SAFE_INTEGER` | `2 ** 53 - 1`. |

## License

MIT
