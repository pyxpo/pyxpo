"""pyxpo-application: expo-application constants, platform checks and the native calls."""
import asyncio
from datetime import datetime, timezone

import pytest

from pyxpo.module_api import ModuleNotLinkedError, NotSupportedError
from pyxpo.module_testing import FakeBridge

import pyxpo_application as Application


def run(coro):
    return asyncio.run(coro)


C = {"applicationName": "Kit", "applicationId": "com.example.kit", "nativeApplicationVersion": "1.2.0",
     "nativeBuildVersion": "7", "androidId": "abcdef0123456789"}


def test_desktop():
    assert Application.application_name is None and Application.applicationId is None
    with pytest.raises(NotSupportedError):
        run(Application.get_installation_time_async())
    with pytest.raises(NotSupportedError):
        Application.get_android_id()
    with pytest.raises(AttributeError):
        Application.nope


def test_ios():
    with FakeBridge("ios", constants={"Application": C}) as fb:
        fb.on("Application", "getInstallationTime", lambda: 1_700_000_000_500.0)
        fb.on("Application", "getIdForVendor", lambda: "A-B")
        fb.on("Application", "getReleaseType", lambda: 1)
        fb.on("Application", "getPushEnvironment", lambda: None)
        assert Application.application_id == Application.applicationId == "com.example.kit"
        assert Application.native_build_version == "7" and Application.nativeApplicationVersion == "1.2.0"
        t = run(Application.get_installation_time_async())
        assert t == datetime(2023, 11, 14, 22, 13, 20, 500000, tzinfo=timezone.utc)
        assert run(Application.get_ios_id_for_vendor_async()) == "A-B"
        assert run(Application.get_ios_application_release_type_async()) is Application.ApplicationReleaseType.SIMULATOR
        assert run(Application.getIosPushNotificationServiceEnvironmentAsync()) is None
        for f in (Application.get_last_update_time_async, Application.get_install_referrer_async):
            with pytest.raises(NotSupportedError):
                run(f())
        with pytest.raises(NotSupportedError):
            Application.get_android_id()


def test_android():
    with FakeBridge("android", constants={"Application": C}) as fb:
        fb.on("Application", "getLastUpdateTime", lambda: 0)
        fb.on("Application", "getInstallReferrer", lambda: "utm_source=google-play")
        assert Application.get_android_id() == "abcdef0123456789"
        assert run(Application.get_last_update_time_async()) == datetime(1970, 1, 1, tzinfo=timezone.utc)
        assert run(Application.get_install_referrer_async()) == "utm_source=google-play"
        with pytest.raises(NotSupportedError):
            run(Application.get_ios_id_for_vendor_async())


def test_unknown_release_type_and_not_linked():
    with FakeBridge("ios", constants={"Application": C}) as fb:
        fb.on("Application", "getReleaseType", lambda: 42)
        assert run(Application.get_ios_application_release_type_async()) is Application.ApplicationReleaseType.UNKNOWN
    with FakeBridge("android"):
        with pytest.raises(ModuleNotLinkedError):
            Application.application_id
