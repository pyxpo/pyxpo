import pytest

from pyxpo.build import android


def _setup(monkeypatch, devices, avds=()):
    monkeypatch.delenv("ANDROID_SERIAL", raising=False)
    monkeypatch.setattr(android, "find_sdk", lambda: android.Path("/sdk"))
    monkeypatch.setattr(android, "adb_path", lambda: "adb")
    monkeypatch.setattr(android, "_devices", lambda adb: list(devices))
    monkeypatch.setattr(android, "list_avds", lambda sdk: list(avds))
    started = []
    monkeypatch.setattr(android, "_start_emulator", lambda sdk, avd, adb: started.append(avd) or "emulator-5554")
    return started


def test_parse_devices():
    out = "List of devices attached\nemulator-5554\tdevice\nR58M\tunauthorized\n\n"
    assert android.parse_devices(out) == [("emulator-5554", "device"), ("R58M", "unauthorized")]


def test_single_device_is_pinned(monkeypatch):
    _setup(monkeypatch, [("R58M", "device")])
    assert android.ensure_device() == "R58M"
    assert android.os.environ["ANDROID_SERIAL"] == "R58M"


def test_no_device_boots_emulator(monkeypatch):
    started = _setup(monkeypatch, [], ["pixel"])
    assert android.ensure_device() == "emulator-5554" and started == ["pixel"]


def test_named_avd_boots_that_one(monkeypatch):
    started = _setup(monkeypatch, [], ["pixel", "tablet"])
    android.ensure_device("tablet")
    assert started == ["tablet"]


def test_several_devices_need_a_choice(monkeypatch):
    _setup(monkeypatch, [("A", "device"), ("B", "device")])
    with pytest.raises(android.BuildError, match="--device"):
        android.ensure_device()
    assert android.ensure_device("B") == "B"


def test_unauthorized_phone_says_why(monkeypatch):
    started = _setup(monkeypatch, [("R58M", "unauthorized")], ["pixel"])
    with pytest.raises(android.BuildError, match="Allow USB debugging"):
        android.ensure_device()
    assert started == []


def test_nothing_at_all(monkeypatch):
    _setup(monkeypatch, [])
    with pytest.raises(android.BuildError, match="Device Manager"):
        android.ensure_device()
