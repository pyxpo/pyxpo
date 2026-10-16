"""The app's own identity: the expo-application API.

    import pyxpo_application as Application

    Application.application_name, Application.application_id        # or Application.applicationName ...
    Application.native_application_version, Application.native_build_version
    installed = await Application.get_installation_time_async()     # datetime (UTC)

The constants are read once at startup from the installed app (Info.plist, PackageInfo). On the desktop
they are None and the functions raise `NotSupportedError`, as there is no installed app.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Optional

from pyxpo.module_api import NotSupportedError, call, constants, platform, require_linked, require_supported

__version__ = "0.1.0a1"

_FIELDS = {
    "applicationName": "application_name", "applicationId": "application_id",
    "nativeApplicationVersion": "native_application_version", "nativeBuildVersion": "native_build_version",
}
_BY_SNAKE = {snake: camel for camel, snake in _FIELDS.items()}


class ApplicationReleaseType(IntEnum):
    """How an iOS build was signed, from its embedded provisioning profile."""
    UNKNOWN = 0
    SIMULATOR = 1
    ENTERPRISE = 2
    DEVELOPMENT = 3
    AD_HOC = 4
    APP_STORE = 5


def _native(feature: str) -> None:
    if platform() == "desktop":
        raise NotSupportedError("%s needs an installed app (iOS or Android)" % feature)
    require_linked("Application", "application", package="pyxpo-application")


def _const(name: str) -> Any:
    if platform() == "desktop":
        return None
    require_linked("Application", "application", package="pyxpo-application")
    return constants("Application").get(name)


def __getattr__(name: str) -> Any:
    # Constants resolve on access: the startup env is not there yet when this module is imported.
    camel = name if name in _FIELDS else _BY_SNAKE.get(name)
    if camel is None:
        raise AttributeError("module 'pyxpo_application' has no attribute %r" % name)
    return _const(camel)


def _time(ms: Any) -> datetime:
    return datetime.fromtimestamp(float(ms) / 1000.0, tz=timezone.utc)


def get_android_id() -> str:
    """Android: the 64-bit hex id unique per app signing key, user and device (`Settings.Secure.ANDROID_ID`).
    It changes on factory reset. Raises `NotSupportedError` on iOS and the desktop."""
    require_supported("get_android_id", ios=False)
    _native("get_android_id")
    return str(_const("androidId"))


async def get_installation_time_async() -> datetime:
    """When the app was installed (UTC). iOS: creation time of the app's Documents folder; Android:
    `PackageInfo.firstInstallTime`."""
    _native("get_installation_time_async")
    return _time(await call("Application", "getInstallationTime", reply=True))


async def get_last_update_time_async() -> datetime:
    """Android: when the app was last installed or updated (UTC, `PackageInfo.lastUpdateTime`)."""
    require_supported("get_last_update_time_async", ios=False)
    _native("get_last_update_time_async")
    return _time(await call("Application", "getLastUpdateTime", reply=True))


async def get_install_referrer_async() -> str:
    """Android: the Google Play install referrer string (`utm_source=...`). Fails where the Play Store is
    missing, for example on emulators without Google Play."""
    require_supported("get_install_referrer_async", ios=False)
    _native("get_install_referrer_async")
    return str(await call("Application", "getInstallReferrer", reply=True))


async def get_ios_id_for_vendor_async() -> Optional[str]:
    """iOS: `identifierForVendor`, the same for all apps of one vendor on the device. None right after a
    restart before the first unlock."""
    require_supported("get_ios_id_for_vendor_async", android=False)
    _native("get_ios_id_for_vendor_async")
    return await call("Application", "getIdForVendor", reply=True)


async def get_ios_application_release_type_async() -> ApplicationReleaseType:
    """iOS: how this build was signed (`SIMULATOR`, `DEVELOPMENT`, `AD_HOC`, `ENTERPRISE`, `APP_STORE`)."""
    require_supported("get_ios_application_release_type_async", android=False)
    _native("get_ios_application_release_type_async")
    v = await call("Application", "getReleaseType", reply=True)
    return ApplicationReleaseType(v) if v in ApplicationReleaseType._value2member_map_ else ApplicationReleaseType.UNKNOWN


async def get_ios_push_notification_service_environment_async() -> Optional[str]:
    """iOS: the `aps-environment` entitlement ("development" or "production"), None when the app has none
    (the Simulator, or no push capability)."""
    require_supported("get_ios_push_notification_service_environment_async", android=False)
    _native("get_ios_push_notification_service_environment_async")
    return await call("Application", "getPushEnvironment", reply=True)


getAndroidId = get_android_id
getInstallationTimeAsync = get_installation_time_async
getLastUpdateTimeAsync = get_last_update_time_async
getInstallReferrerAsync = get_install_referrer_async
getIosIdForVendorAsync = get_ios_id_for_vendor_async
getIosApplicationReleaseTypeAsync = get_ios_application_release_type_async
getIosPushNotificationServiceEnvironmentAsync = get_ios_push_notification_service_environment_async

__all__ = [
    "ApplicationReleaseType", "get_android_id", "get_installation_time_async", "get_last_update_time_async",
    "get_install_referrer_async", "get_ios_id_for_vendor_async", "get_ios_application_release_type_async",
    "get_ios_push_notification_service_environment_async", "getAndroidId", "getInstallationTimeAsync",
    "getLastUpdateTimeAsync", "getInstallReferrerAsync", "getIosIdForVendorAsync",
    "getIosApplicationReleaseTypeAsync", "getIosPushNotificationServiceEnvironmentAsync",
] + list(_FIELDS) + list(_FIELDS.values())
