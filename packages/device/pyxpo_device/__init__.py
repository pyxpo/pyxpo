"""Facts about the device the app runs on: the expo-device API.

    import pyxpo_device as Device

    Device.brand, Device.model_name, Device.os_name, Device.os_version   # or Device.modelName, Device.osName ...
    if Device.device_type == Device.DeviceType.TABLET: ...
    ms = await Device.get_uptime_async()

The constants are read once at startup (no bridge round trip). Values a platform does not have are None:
`model_id` is iOS only; `design_name`, `product_name`, `os_build_fingerprint` and `platform_api_level` are
Android only. `device_year_class` is the release year of the iPhone model (None for unknown models and on
Android). On the desktop the values come from Python's `platform` module.
"""
from __future__ import annotations

import os
import platform as _py_platform
import sys
import time
from enum import IntEnum
from typing import Any, Dict, List, Optional

from pyxpo.module_api import call, constants, platform, require_linked

__version__ = "0.1.0a1"

# Number.MAX_SAFE_INTEGER: what expo-device returns when memory has no inherent limit.
MAX_SAFE_INTEGER = 2 ** 53 - 1


class DeviceType(IntEnum):
    """Kind of device, from the screen size and the platform's own idiom."""
    UNKNOWN = 0
    PHONE = 1
    TABLET = 2
    DESKTOP = 3
    TV = 4


_FIELDS = {
    "isDevice": "is_device", "brand": "brand", "manufacturer": "manufacturer", "modelName": "model_name",
    "modelId": "model_id", "designName": "design_name", "productName": "product_name",
    "deviceYearClass": "device_year_class", "totalMemory": "total_memory",
    "supportedCpuArchitectures": "supported_cpu_architectures", "osName": "os_name", "osVersion": "os_version",
    "osBuildId": "os_build_id", "osInternalBuildId": "os_internal_build_id",
    "osBuildFingerprint": "os_build_fingerprint", "platformApiLevel": "platform_api_level",
    "deviceName": "device_name", "deviceType": "device_type",
}
_BY_SNAKE = {snake: camel for camel, snake in _FIELDS.items()}


def _native() -> bool:
    if platform() == "desktop":
        return False
    require_linked("Device", "device", package="pyxpo-device")
    return True


def _desktop() -> Dict[str, Any]:
    u = _py_platform.uname()
    total: Optional[int] = None
    try:
        total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, ValueError, OSError):
        pass
    return {
        "isDevice": True, "brand": None, "manufacturer": None, "modelName": None, "modelId": None,
        "designName": None, "productName": None, "deviceYearClass": None, "totalMemory": total,
        "supportedCpuArchitectures": [u.machine] if u.machine else None, "osName": u.system or sys.platform,
        "osVersion": u.release or None, "osBuildId": u.version or None, "osInternalBuildId": u.version or None,
        "osBuildFingerprint": None, "platformApiLevel": None, "deviceName": u.node or None,
        "deviceType": int(DeviceType.DESKTOP),
    }


def _all() -> Dict[str, Any]:
    if not _native():
        return _desktop()
    c = constants("Device")
    return {k: c.get(k) for k in _FIELDS}


def __getattr__(name: str) -> Any:
    # Constants resolve on access: the startup env is not there yet when this module is imported.
    camel = name if name in _FIELDS else _BY_SNAKE.get(name)
    if camel is None:
        raise AttributeError("module 'pyxpo_device' has no attribute %r" % name)
    value = _all()[camel]
    if camel == "deviceType":
        return DeviceType(value) if value in DeviceType._value2member_map_ else DeviceType.UNKNOWN
    if camel == "supportedCpuArchitectures" and value is not None:
        return list(value)
    return value


async def get_device_type_async() -> DeviceType:
    """The `DeviceType` of this device (same as `device_type`)."""
    return __getattr__("deviceType")


async def get_uptime_async() -> int:
    """Milliseconds since the device booted, not counting deep sleep."""
    if not _native():
        return int(time.monotonic() * 1000)  # the system clock since boot on macOS and Linux
    return int(await call("Device", "getUptime", reply=True))


async def get_max_memory_async() -> int:
    """Most memory (bytes) the Android runtime lets the app use. `MAX_SAFE_INTEGER` where there is no limit
    (iOS, the desktop)."""
    if platform() != "android" or not _native():
        return MAX_SAFE_INTEGER
    return int(await call("Device", "getMaxMemory", reply=True))


async def is_rooted_experimental_async() -> bool:
    """Best-effort jailbreak (iOS) or root (Android) check. Easy to fool: never use it for security."""
    if not _native():
        return False
    return bool(await call("Device", "isRooted", reply=True))


async def is_side_loading_enabled_async() -> bool:
    """Android: whether this app may install other apps (needs REQUEST_INSTALL_PACKAGES on Android 8+).
    Always False on iOS and the desktop."""
    if platform() != "android" or not _native():
        return False
    return bool(await call("Device", "isSideLoadingEnabled", reply=True))


async def get_platform_features_async() -> List[str]:
    """Android: the system feature names the device reports (`PackageManager.getSystemAvailableFeatures`).
    Empty on iOS and the desktop."""
    if platform() != "android" or not _native():
        return []
    return list(await call("Device", "getPlatformFeatures", reply=True) or [])


async def has_platform_feature_async(feature: str) -> bool:
    """Android: whether the device has a system feature, for example "android.hardware.camera".
    Always False on iOS and the desktop."""
    if not isinstance(feature, str) or not feature:
        raise ValueError("feature must be a non-empty string")
    if platform() != "android" or not _native():
        return False
    return bool(await call("Device", "hasPlatformFeature", feature, reply=True))


getDeviceTypeAsync = get_device_type_async
getUptimeAsync = get_uptime_async
getMaxMemoryAsync = get_max_memory_async
isRootedExperimentalAsync = is_rooted_experimental_async
isSideLoadingEnabledAsync = is_side_loading_enabled_async
getPlatformFeaturesAsync = get_platform_features_async
hasPlatformFeatureAsync = has_platform_feature_async

__all__ = [
    "DeviceType", "MAX_SAFE_INTEGER", "get_device_type_async", "get_uptime_async", "get_max_memory_async",
    "is_rooted_experimental_async", "is_side_loading_enabled_async", "get_platform_features_async",
    "has_platform_feature_async", "getDeviceTypeAsync", "getUptimeAsync", "getMaxMemoryAsync",
    "isRootedExperimentalAsync", "isSideLoadingEnabledAsync", "getPlatformFeaturesAsync",
    "hasPlatformFeatureAsync",
] + list(_FIELDS) + list(_FIELDS.values())
