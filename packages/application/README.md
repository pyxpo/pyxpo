# pyxpo-application

The installed app's own identity for [pyxpo](https://github.com/pyxpo/pyxpo) apps: name, id, version,
build number, install time and signing details. The API follows
[expo-application](https://docs.expo.dev/versions/latest/sdk/application/).

```sh
pip install pyxpo-application
```

```toml
[tool.pyxpo]
modules = ["application"]
```

```python
import pyxpo_application as Application

print(Application.application_name, Application.application_id)
print(Application.native_application_version, Application.native_build_version)
installed = await Application.get_installation_time_async()   # timezone-aware datetime (UTC)
```

Every name also has its expo-application spelling (`Application.applicationId`,
`Application.getInstallationTimeAsync`).

## Constants

Read once at app start. `None` on the desktop.

- `application_name`: the name on the home screen
- `application_id`: bundle identifier (iOS) or package name (Android)
- `native_application_version`: `CFBundleShortVersionString` / `versionName`, for example `"1.2.0"`
- `native_build_version`: `CFBundleVersion` / `versionCode`, as a string

## Functions

| Function | Platforms | Returns |
| --- | --- | --- |
| `get_installation_time_async()` | iOS, Android | `datetime` (UTC). iOS: creation time of the Documents folder |
| `get_last_update_time_async()` | Android | `datetime` (UTC) of the last install or update |
| `get_android_id()` | Android | `ANDROID_ID`: unique per signing key, user and device; changes on factory reset |
| `get_install_referrer_async()` | Android | Google Play install referrer. Fails without the Play Store (most emulators) |
| `get_ios_id_for_vendor_async()` | iOS | `identifierForVendor`, or None before the first unlock |
| `get_ios_application_release_type_async()` | iOS | `ApplicationReleaseType`: `SIMULATOR`, `DEVELOPMENT`, `AD_HOC`, `ENTERPRISE`, `APP_STORE` |
| `get_ios_push_notification_service_environment_async()` | iOS | `"development"`, `"production"` or None |

Calling a function on a platform it does not list raises `NotSupportedError`; so does every function on
the desktop.

On Android the module adds the `com.android.installreferrer:installreferrer` library.

## Permissions

None.
