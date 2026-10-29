# pyxpo-application

The installed app's own identity for [pyxpo](https://github.com/pyxpo/pyxpo) apps, written in Python: app name,
bundle or package id, version, build number, install and update time, and the signing details of the build. The
names follow [expo-application](https://docs.expo.dev/versions/latest/sdk/application/), in Python style.

<p align="center">
  <img src="https://raw.githubusercontent.com/pyxpo/pyxpo-application/main/docs/images/hero.png" width="820" alt="The application module on Android and iOS: name, id, version, build, install time and platform ids">
</p>

```python
import pyxpo_application as Application

print(Application.application_name, Application.application_id)            # "Package Showcase", "com.example.pkgshow"
print(Application.native_application_version, Application.native_build_version)   # "1.2.0", "1"
installed = await Application.get_installation_time_async()                # datetime, UTC
```

## Features

- **Four constants, no calls:** name, id, version and build number are read once at startup and are plain
  attributes of the module.
- **Install and update time:** `get_installation_time_async()` on both platforms, `get_last_update_time_async()`
  on Android. Both return timezone-aware `datetime` objects in UTC.
- **Platform ids:**
  - Android: `get_android_id()` and the Google Play install referrer.
  - iOS: `identifierForVendor`, how the build was signed (development, ad hoc, App Store, Simulator) and the
    push environment.
- **Honest on the wrong platform:** a call that does not exist on this platform raises `NotSupportedError` with a
  message that names the feature. Nothing returns a made-up value.
- **No permissions:** nothing here needs a prompt, an entitlement or a manifest entry.
- **Typed:** ships `py.typed`. Every name also has its expo-application spelling (`Application.applicationId`,
  `Application.getInstallationTimeAsync`).

## Contents

| If you are... | Start here |
| --- | --- |
| Showing the version in an About screen | [Quick start](#quick-start) → [Constants](#constants) |
| Checking for an old install or a fresh update | [Install and update time](#install-and-update-time) |
| Telling a test build from the store build | [iOS release type](#ios-release-type-and-push-environment) |
| Needing a device-bound id | [Platform ids](#platform-ids) |
| Looking for exact signatures | [API reference](#api-reference) · [Errors](#errors) |
| Seeing it in a real app | [Recipe: an About screen and an update check](#recipe-an-about-screen-and-an-update-check) |
| Stuck | [Testing](#testing) · [Troubleshooting](#troubleshooting) · [FAQ](#faq) |

## Platform support

| Target | What works |
| --- | --- |
| Android, API 24+ | All constants. `get_installation_time_async`, `get_last_update_time_async`, `get_android_id`, `get_install_referrer_async`. |
| iOS | All constants. `get_installation_time_async`, `get_ios_id_for_vendor_async`, `get_ios_application_release_type_async`, `get_ios_push_notification_service_environment_async`. |
| Web page and desktop window (`pyxpo run web` / `pyxpo run desktop`) | Constants are `None` and every function raises `NotSupportedError`, because there is no installed app. |

Requires Python 3.9+ and `pyxpo>=0.1.0a2`.

## Install

```sh
pip install pyxpo-application
```

Add the module to your app's `pyproject.toml`:

```toml
[tool.pyxpo]
modules = ["application"]
```

The module has native code, so rebuild the app after adding it (`pyxpo run android` or `pyxpo run ios`). On
Android it adds the `com.android.installreferrer:installreferrer` library.

## Quick start

```python
import pyxpo_application as Application
from pyxpo import Platform, Text, View, component, use_async


@component
def About():
    async def load():
        info = {"installed": await Application.get_installation_time_async()}
        if Platform.OS == "android":
            info["updated"] = await Application.get_last_update_time_async()
        return info

    info = use_async(load, [])           # (loading, value, error)
    return View(
        Text("%s %s (%s)" % (Application.application_name,
                             Application.native_application_version,
                             Application.native_build_version)),
        Text(Application.application_id),
        Text("Installed %s" % (info.value["installed"].date() if info.value else "...")),
    )
```

> **Tip:** the constants resolve when you read them, not when the module is imported, because the startup
> environment is not there yet at import time. Read them inside a component or a function, as above. Do not copy
> them into module-level variables at import.

## Constants

Read once at app start from `Info.plist` (iOS) and `PackageInfo` (Android). `None` on the desktop.

| Python name | expo name | iOS | Android |
| --- | --- | --- | --- |
| `application_name` | `applicationName` | `CFBundleDisplayName` or `CFBundleName` | the app label |
| `application_id` | `applicationId` | bundle identifier | package name |
| `native_application_version` | `nativeApplicationVersion` | `CFBundleShortVersionString` | `versionName` |
| `native_build_version` | `nativeBuildVersion` | `CFBundleVersion` | `versionCode`, as a string |

<p align="center">
  <img src="https://raw.githubusercontent.com/pyxpo/pyxpo-application/main/docs/images/identity.png" width="720" alt="Constants and ids on Android and iOS">
</p>

## Install and update time

```python
installed = await Application.get_installation_time_async()      # both platforms
updated = await Application.get_last_update_time_async()         # Android only
```

| Function | Returns | Where it comes from |
| --- | --- | --- |
| `get_installation_time_async()` | `datetime` (UTC) | iOS: creation time of the app's Documents folder. Android: `PackageInfo.firstInstallTime`. |
| `get_last_update_time_async()` | `datetime` (UTC) | Android: `PackageInfo.lastUpdateTime`. |

On iOS the install time is the first launch of this install, not a store download date. Deleting and reinstalling
the app gives a new date.

## Platform ids

```python
Application.get_android_id()                          # Android: "9b1e4f0c2a7d5e38"
await Application.get_ios_id_for_vendor_async()       # iOS: "F3C1D6B2-..."
await Application.get_install_referrer_async()        # Android: "utm_source=google-play&utm_medium=organic"
```

| Function | Notes |
| --- | --- |
| `get_android_id()` | `Settings.Secure.ANDROID_ID`. A 64-bit hex string, unique per app signing key, user and device. It changes on a factory reset. Synchronous. |
| `get_ios_id_for_vendor_async()` | `identifierForVendor`. The same for every app of one vendor on a device, new after all of the vendor's apps are removed. `None` right after a restart, before the first unlock. |
| `get_install_referrer_async()` | The Google Play install referrer string. Fails where the Play Store is missing, such as most emulators. |

These ids are not secret and not stable forever. Do not use them as a login or for ads attribution without telling
the user (see the store rules for your platform).

## iOS release type and push environment

```python
kind = await Application.get_ios_application_release_type_async()
if kind == Application.ApplicationReleaseType.APP_STORE:
    ...
env = await Application.get_ios_push_notification_service_environment_async()   # "development", "production" or None
```

`ApplicationReleaseType` is an `IntEnum`:

| Value | Meaning |
| --- | --- |
| `UNKNOWN` (0) | The profile could not be read. |
| `SIMULATOR` (1) | Running in the iOS Simulator. |
| `ENTERPRISE` (2) | Enterprise distribution. |
| `DEVELOPMENT` (3) | A development profile (run from Xcode). |
| `AD_HOC` (4) | An ad hoc profile. |
| `APP_STORE` (5) | The App Store or TestFlight. |

The release type is read from the embedded provisioning profile. The push environment is the `aps-environment`
entitlement, `None` when the app has none (the Simulator, or no push capability).

## Errors

| Error | When | What to do |
| --- | --- | --- |
| `NotSupportedError` | A function is called on a platform it does not list, or any function on the desktop. | Guard with `Platform.OS`, or catch it. |
| `ModuleNotLinkedError` (from `pyxpo.module_api`) | The app was built without `"application"` in `modules`. | Add it and rebuild. |
| `RuntimeError` from `get_install_referrer_async` | No Play Store on the device. | Treat the referrer as unknown. |

## Config

There are no module options and no config plugin. The only native setup is the `modules` entry.

## Web and desktop

There is no installed app, so the four constants are `None` and every function raises `NotSupportedError`. Write
UI code so that a `None` version shows a placeholder:

```python
version = Application.native_application_version or "dev"
```

## Recipe: an About screen and an update check

Show the version, and tell the user "Updated recently" when Android has installed a new build in the last week.

```python
from datetime import datetime, timedelta, timezone

import pyxpo_application as Application
from pyxpo import Platform, Text, View, component, use_async


async def recently_updated() -> bool:
    if Platform.OS != "android":
        return False
    updated = await Application.get_last_update_time_async()
    return datetime.now(timezone.utc) - updated < timedelta(days=7)


@component
def AboutScreen():
    fresh = use_async(recently_updated, [])
    return View(
        Text(Application.application_name or "My app"),
        Text("Version %s (%s)" % (Application.native_application_version or "dev",
                                  Application.native_build_version or "0")),
        Text("Updated recently") if fresh.value else None,
    )
```

## Production checklist

- [ ] Version and build number are set in `[tool.pyxpo]` (or `pyproject.toml`), and the About screen shows the
      same values the store shows.
- [ ] Code that uses `get_android_id()` or `get_ios_id_for_vendor_async()` is covered by your privacy policy.
- [ ] Calls that are platform specific are guarded with `Platform.OS`.
- [ ] A missing Play Store (`get_install_referrer_async`) does not break the first launch.
- [ ] The desktop and web fallbacks (`None`) are handled in the UI.

## Testing

The module reads the native side through `pyxpo.module_api`. In a unit test, patch the constants and the functions
with a fake:

```python
import pyxpo_application as Application


def test_about_text(monkeypatch):
    fake = {"applicationName": "Demo", "nativeApplicationVersion": "2.0.0"}
    monkeypatch.setattr(Application, "_const", lambda name: fake.get(name))
    assert Application.application_name == "Demo"
    assert Application.native_application_version == "2.0.0"
```

On the desktop test host (no phone), `Application.application_name` is `None` and every function raises
`NotSupportedError`, so tests for UI code can also just assert the fallback text.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `NotSupportedError: ... needs an installed app` | You are on `pyxpo run web` or `pyxpo run desktop`. Run on a phone or emulator, or fake it. |
| A constant is `None` on a phone | The module was not built in. Add `"application"` to `modules` and rebuild. |
| `get_install_referrer_async` raises | The device has no Google Play. Use a Google Play emulator image or a real phone. |
| `get_ios_id_for_vendor_async` returns `None` | The phone was restarted and not yet unlocked. Retry after unlock. |
| Install time looks wrong on iOS | It is the Documents folder creation time, so a reinstall gives a new date. |
| `get_last_update_time_async` raises on iOS | Android only. |

## FAQ

**Is the version the same as the one in my `pyproject.toml`?** The version and build you set for the app are
written into `Info.plist` and the Android manifest at build time, and this module reads them back from the
installed app.

**Can I get the Android `versionCode` as a number?** `native_build_version` is a string on both platforms. Use
`int(...)`.

**Does it work in the iOS Simulator?** Yes. The release type is `SIMULATOR` and the push environment is `None`.

**Why a `datetime` and not a timestamp?** The values are timezone-aware UTC `datetime` objects. Use `.timestamp()`
if you need a number.

## API reference

### Constants

| Python name | expo name | Type |
| --- | --- | --- |
| `application_name` | `applicationName` | `str` or `None` |
| `application_id` | `applicationId` | `str` or `None` |
| `native_application_version` | `nativeApplicationVersion` | `str` or `None` |
| `native_build_version` | `nativeBuildVersion` | `str` or `None` |

### Functions

| Function (expo name) | Platforms | Returns |
| --- | --- | --- |
| `get_installation_time_async()` (`getInstallationTimeAsync`) | iOS, Android | `datetime` (UTC) |
| `get_last_update_time_async()` (`getLastUpdateTimeAsync`) | Android | `datetime` (UTC) |
| `get_android_id()` (`getAndroidId`) | Android | `str` |
| `get_install_referrer_async()` (`getInstallReferrerAsync`) | Android | `str` |
| `get_ios_id_for_vendor_async()` (`getIosIdForVendorAsync`) | iOS | `str` or `None` |
| `get_ios_application_release_type_async()` (`getIosApplicationReleaseTypeAsync`) | iOS | `ApplicationReleaseType` |
| `get_ios_push_notification_service_environment_async()` (`getIosPushNotificationServiceEnvironmentAsync`) | iOS | `str` or `None` |

### Types

| Name | Description |
| --- | --- |
| `ApplicationReleaseType` | `IntEnum`: `UNKNOWN`, `SIMULATOR`, `ENTERPRISE`, `DEVELOPMENT`, `AD_HOC`, `APP_STORE`. |
| `NotSupportedError` | Raised for a missing platform feature (from `pyxpo.module_api`). |

## License

MIT
