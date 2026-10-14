import importlib
import os
import plistlib
import re
from pathlib import Path

ios = importlib.import_module("pyxpo.build.ios")
ios_wrap = importlib.import_module("pyxpo.build.ios_wrap")


def test_module_name():
    assert ios_wrap.module_name("numpy/core/_x.cpython-313-iphoneos.so") == "numpy.core._x"
    assert ios_wrap.module_name("_struct.cpython-313-iphonesimulator.so") == "_struct"


def test_wrap_fake_bundle(tmp_path):
    b = tmp_path / "b"
    ext = b / "app_packages" / "pkg" / "_c.cpython-313-iphoneos.so"
    ext.parent.mkdir(parents=True)
    ext.write_bytes(b"\xcf\xfa\xed\xfe")
    tpl = tmp_path / "t.plist"
    tpl.write_bytes(plistlib.dumps({"CFBundleName": "x"}))
    fws = ios_wrap.wrap(str(b), str(tpl), "dev.x.app", "iPhoneSimulator")
    assert len(fws) == 1
    fw = b / "Frameworks" / "pkg._c.framework"
    assert (fw / "pkg._c").is_file() and not ext.exists()
    assert (ext.parent / "_c.cpython-313-iphoneos.fwork").read_text() == "Frameworks/pkg._c.framework/pkg._c"
    assert (fw / "pkg._c.origin").read_text() == "app_packages/pkg/_c.cpython-313-iphoneos.fwork"
    info = plistlib.loads((fw / "Info.plist").read_bytes())
    assert info["MinimumOSVersion"] == "15.0" and info["CFBundleExecutable"] == "pkg._c"


def test_pick_simulator_prefers_booted():
    data = {"devices": {
        "com.apple.CoreSimulator.SimRuntime.iOS-26-0": [{"name": "iPhone 17", "udid": "A", "state": "Shutdown"}],
        "com.apple.CoreSimulator.SimRuntime.iOS-27-0": [{"name": "iPhone 18", "udid": "B", "state": "Shutdown"}],
        "com.apple.CoreSimulator.SimRuntime.watchOS-27-0": [{"name": "iPhone X", "udid": "W", "state": "Booted"}],
    }}
    assert ios.pick_simulator(data)["udid"] == "B"
    data["devices"]["com.apple.CoreSimulator.SimRuntime.iOS-26-0"][0]["state"] = "Booted"
    assert ios.pick_simulator(data)["udid"] == "A"
    assert ios.pick_simulator({"devices": {}}) is None


def test_launch_env_prefix():
    env = ios.launch_env({"PYXPO_DEV_URL": "http://127.0.0.1:1"})
    assert env["SIMCTL_CHILD_PYXPO_DEV_URL"] == "http://127.0.0.1:1"


def test_render_shell_no_placeholders(tmp_path, monkeypatch):
    monkeypatch.setattr(ios, "DIST", tmp_path / "dist")
    (tmp_path / "dist" / "Python.xcframework").mkdir(parents=True)
    dest = tmp_path / "shell"
    ios.render_shell(dest, {"app_id": "dev.x.app", "product_name": "x", "app_name": "X"})
    assert (dest / "native" / "pyxpo_bridge.c").is_file()
    for p in dest.rglob("*"):
        if p.is_file() and not p.is_symlink() and p.suffix in ios.TEXT_SUFFIXES:
            assert not re.search(r"\{\{\w+\}\}", p.read_text()), p
