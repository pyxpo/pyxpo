"""pyxpo-device: expo-device constants (both spellings), desktop values and the native calls."""
import asyncio

import pytest

from pyxpo.module_testing import FakeBridge

import pyxpo_device as Device


def run(coro):
    return asyncio.run(coro)


IOS = {"isDevice": False, "brand": "Apple", "manufacturer": "Apple", "modelName": "iPhone 16", "modelId": "iPhone17,3",
       "designName": None, "productName": None, "deviceYearClass": 2024, "totalMemory": 8 << 30,
       "supportedCpuArchitectures": ["arm64"], "osName": "iOS", "osVersion": "26.0", "osBuildId": "23A1",
       "osInternalBuildId": "23A1", "osBuildFingerprint": None, "platformApiLevel": None, "deviceName": "iPhone",
       "deviceType": 1}


def test_desktop_values():
    assert Device.device_type == Device.DeviceType.DESKTOP
    assert Device.deviceType is Device.DeviceType.DESKTOP
    assert Device.is_device is True and isinstance(Device.os_name, str)
    assert Device.model_id is None and Device.platformApiLevel is None
    assert run(Device.get_uptime_async()) > 0
    assert run(Device.get_max_memory_async()) == Device.MAX_SAFE_INTEGER
    assert run(Device.is_rooted_experimental_async()) is False
    assert run(Device.get_platform_features_async()) == []
    assert run(Device.has_platform_feature_async("android.hardware.camera")) is False
    assert run(Device.getDeviceTypeAsync()) == Device.DeviceType.DESKTOP
    with pytest.raises(AttributeError):
        Device.nope
    with pytest.raises(ValueError):
        run(Device.has_platform_feature_async(""))


def test_ios_constants_and_calls():
    with FakeBridge("ios", constants={"Device": IOS}) as fb:
        fb.on("Device", "getUptime", lambda: 1234)
        fb.on("Device", "isRooted", lambda: False)
        assert Device.model_name == Device.modelName == "iPhone 16"
        assert Device.model_id == "iPhone17,3" and Device.device_year_class == 2024
        assert Device.device_type is Device.DeviceType.PHONE
        archs = Device.supported_cpu_architectures
        archs.append("x")
        assert Device.supportedCpuArchitectures == ["arm64"]
        assert run(Device.get_uptime_async()) == 1234
        assert run(Device.is_rooted_experimental_async()) is False
        # Android-only functions answer without a native call on iOS.
        assert run(Device.get_max_memory_async()) == Device.MAX_SAFE_INTEGER
        assert run(Device.is_side_loading_enabled_async()) is False
        assert run(Device.get_platform_features_async()) == []
        assert run(Device.has_platform_feature_async("x")) is False
        assert fb.calls == [("Device", "getUptime", ()), ("Device", "isRooted", ())]


def test_android_calls_and_unknown_type():
    consts = dict(IOS, brand="google", deviceType=9, platformApiLevel=37)
    with FakeBridge("android", constants={"Device": consts}) as fb:
        fb.on("Device", "getMaxMemory", lambda: 512 << 20)
        fb.on("Device", "isSideLoadingEnabled", lambda: False)
        fb.on("Device", "getPlatformFeatures", lambda: ["android.hardware.wifi"])
        fb.on("Device", "hasPlatformFeature", lambda f: f == "android.hardware.wifi")
        assert Device.brand == "google" and Device.platform_api_level == 37
        assert Device.device_type is Device.DeviceType.UNKNOWN
        assert run(Device.get_max_memory_async()) == 512 << 20
        assert run(Device.is_side_loading_enabled_async()) is False
        assert run(Device.get_platform_features_async()) == ["android.hardware.wifi"]
        assert run(Device.has_platform_feature_async("android.hardware.wifi")) is True
        assert fb.calls[-1] == ("Device", "hasPlatformFeature", ("android.hardware.wifi",))


def test_not_linked():
    from pyxpo.module_api import ModuleNotLinkedError
    with FakeBridge("android"):
        with pytest.raises(ModuleNotLinkedError):
            Device.brand
        with pytest.raises(ModuleNotLinkedError):
            run(Device.get_uptime_async())
