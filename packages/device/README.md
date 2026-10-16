# pyxpo-device

Facts about the device a [pyxpo](https://github.com/pyxpo/pyxpo) app runs on: brand, model, OS, memory and
device type. The API follows [expo-device](https://docs.expo.dev/versions/latest/sdk/device/).

```sh
pip install pyxpo-device
```

```toml
[tool.pyxpo]
modules = ["device"]
```

```python
import pyxpo_device as Device

print(Device.brand, Device.model_name, Device.os_name, Device.os_version)
if Device.device_type == Device.DeviceType.TABLET:
    ...
uptime_ms = await Device.get_uptime_async()
```

Every name also has its expo-device spelling (`Device.modelName`, `Device.getUptimeAsync`).

## Constants

Read once at app start, no bridge round trip. `None` where a platform has no value.

| Name | iOS | Android |
| --- | --- | --- |
| `is_device` | False on the Simulator | False on an emulator (best-effort check) |
| `brand`, `manufacturer` | `"Apple"` | `Build.BRAND`, `Build.MANUFACTURER` |
| `model_name` | Marketing name for known iPhones, else the identifier | `Build.MODEL` |
| `model_id` | Identifier, for example `"iPhone17,3"` | None |
| `design_name`, `product_name` | None | `Build.DEVICE`, `Build.PRODUCT` |
| `device_year_class` | Release year of known iPhones | None |
| `total_memory` | Bytes of RAM | Bytes of RAM |
| `supported_cpu_architectures` | `["arm64"]` | `Build.SUPPORTED_ABIS` |
| `os_name` | `"iOS"` or `"iPadOS"` | `"Android"` |
| `os_version` | For example `"26.0"` | For example `"15"` |
| `os_build_id`, `os_internal_build_id` | Kernel OS build | `Build.DISPLAY`, `Build.ID` |
| `os_build_fingerprint`, `platform_api_level` | None | `Build.FINGERPRINT`, API level |
| `device_name` | `UIDevice.name` (a generic name on iOS 16+) | Device name setting, else the model |
| `device_type` | `DeviceType` from the interface idiom | `DeviceType` from TV mode and screen width (600dp+ = tablet) |

On the desktop the values come from Python's `platform` module and `device_type` is `DESKTOP`.

## Functions

- `get_device_type_async()` -> `DeviceType`
- `get_uptime_async()` -> milliseconds since boot, not counting deep sleep
- `get_max_memory_async()` -> Android: the runtime's memory limit in bytes; elsewhere `MAX_SAFE_INTEGER`
- `is_rooted_experimental_async()` -> best-effort jailbreak or root check. Easy to fool; never use it for security.
- `is_side_loading_enabled_async()` -> Android: whether the app may install apps (needs `REQUEST_INSTALL_PACKAGES` on Android 8+)
- `get_platform_features_async()` -> Android system feature names; `[]` elsewhere
- `has_platform_feature_async(feature)` -> Android: for example `"android.hardware.camera"`; `False` elsewhere

## Permissions

None.
