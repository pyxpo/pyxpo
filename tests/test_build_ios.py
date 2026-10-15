import importlib
import pytest
import os
import plistlib
import re
import zipfile
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


def _fake_dist(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    sl = dist / "Python.xcframework" / "ios-arm64-simulator"
    (sl / "lib" / "python3.13").mkdir(parents=True)
    (sl / "lib" / "python3.13" / "os.py").write_text("")
    common = tmp_path / "common"
    common.mkdir()
    for f in ios.NATIVE_FILES:
        (common / f).write_text("/* x */")
    monkeypatch.setattr(ios, "DIST", dist)
    monkeypatch.setattr(ios, "COMMON", common)
    return dist


def _project(tmp_path, extra=""):
    proj = tmp_path / "proj"
    (proj / "app").mkdir(parents=True)
    (proj / "app" / "index.py").write_text("x = 1\n")
    (proj / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "2.3.4"\n[tool.pyxpo]\nname = "Demo App"\nbundle_id = "dev.x.demo"\n' + extra)
    return proj


def test_prebuild_ejects_and_preserves_user_edits(tmp_path, monkeypatch):
    _fake_dist(tmp_path, monkeypatch)
    proj = _project(tmp_path, '[tool.pyxpo.ios]\nteam_id = "ABCDE12345"\n')
    dest = ios.prebuild(proj)
    assert dest == proj / "ios"
    assert (dest / "project.yml").is_file() and (dest / "App" / "AppDelegate.swift").is_file()
    assert (dest / "pyxpo-gen" / "native" / "pyxpo_bridge.c").is_file()
    xc = (dest / "pyxpo-gen" / "Pyxpo.xcconfig").read_text()
    for line in ("PRODUCT_BUNDLE_IDENTIFIER = dev.x.demo", "PYXPO_DISPLAY_NAME = Demo App", "MARKETING_VERSION = 2.3.4",
                 "DEVELOPMENT_TEAM = ABCDE12345", "PYXPO_SCHEME = dev.x.demo"):
        assert line in xc
    assert "pyxpo-gen/" in (dest / ".gitignore").read_text()
    (dest / "App" / "AppDelegate.swift").write_text("// mine\n")
    ios.prebuild(proj)
    assert (dest / "App" / "AppDelegate.swift").read_text() == "// mine\n"
    assert (dest / "App" / "AppDelegate.swift.pyxpo-new").is_file()
    ios.prebuild(proj, clean=True)
    assert "mine" not in (dest / "App" / "AppDelegate.swift").read_text()


def test_stage_keeps_user_files_and_leaves_no_placeholders(tmp_path, monkeypatch):
    _fake_dist(tmp_path, monkeypatch)
    monkeypatch.setattr(ios, "_run", lambda *a, **k: None)
    proj = _project(tmp_path, 'modules = ["sharing"]\n')
    native = ios.prebuild(proj)
    (native / "project.yml").write_text("# edited\nGENERATE_INFOPLIST_FILE: YES\nINFOPLIST_FILE: $(PYXPO_INFOPLIST)\n")
    ios.stage(native, proj, ios.load_config(proj), False, "simulator")
    assert (native / "project.yml").read_text().startswith("# edited")
    root = native / "pyxpo-gen" / "stage" / "app_root"
    assert (root / "app" / "index.py").is_file()
    # the linked module's Python (an installed pip package) ships with the app; unlinked ones and native sources do not
    assert (root / "pyxpo_sharing" / "__init__.py").is_file() and (root / "pyxpo" / "modules.py").is_file()
    assert not (root / "pyxpo_sharing" / "ios").exists() and not (root / "pyxpo_image_manipulator").exists()
    for p in native.rglob("*"):
        if p.is_file() and not p.is_symlink() and p.suffix in (".yml", ".plist", ".swift", ".sh", ".h", ".m", ".xcconfig"):
            text = p.read_text()
            assert not re.search(r"\{\{\w+\}\}", text), p
            if "pyxpo-gen" not in p.parts:
                assert str(tmp_path) not in text, p


def test_android_prebuild_and_stage(tmp_path, monkeypatch):
    droid = importlib.import_module("pyxpo.build.android")
    dist = tmp_path / "adist"
    (dist / "arm64-v8a" / "prefix" / "lib" / "python3.13").mkdir(parents=True)
    for so in droid.SO_FOR_JNILIBS + ["libpython3.13.so"]:
        (dist / "arm64-v8a" / "prefix" / "lib" / so).write_bytes(b"\x7fELF")
    monkeypatch.setattr(droid, "DIST", dist)
    monkeypatch.setattr(droid, "_run", lambda *a, **k: None)
    monkeypatch.setattr(droid, "_check_16kb", lambda *a, **k: None)
    monkeypatch.setenv("ANDROID_HOME", str(tmp_path))
    proj = _project(tmp_path, 'scheme = "demo"\nmodules = ["sharing"]\n[tool.pyxpo.android]\nkeystore = "release.jks"\nkey_alias = "k"\n')
    dest = droid.prebuild(proj)
    props = (dest / "pyxpo-gen" / "pyxpo.properties").read_text()
    assert "applicationId=dev.x.demo" in props and "scheme=demo" in props and "versionName=2.3.4" in props
    assert "release.jks" in props and "assword" not in props
    gradle = dest / "app" / "build.gradle.kts"
    gradle.write_text("// mine\n")  # an old ejected project without the native-module line
    with pytest.raises(droid.BuildError, match="native-module line"):
        droid.stage(dest, proj, droid.load_config(proj), False, ["arm64-v8a"])
    gradle.write_text('// mine\napply(from = "../pyxpo-gen/modules.app.gradle.kts")\n')
    droid.stage(dest, proj, droid.load_config(proj), False, ["arm64-v8a"])
    assert gradle.read_text().startswith("// mine\n")
    names = zipfile.ZipFile(str(dest / "pyxpo-gen" / "assets" / "pyxpo" / "app.zip")).namelist()
    assert "pyxpo_sharing/__init__.py" in names and "pyxpo/modules.py" in names
    assert not [n for n in names if n.startswith("pyxpo_image_manipulator/") or n.endswith((".kt", ".swift", ".json"))]
    assert (dest / "pyxpo-gen" / "modules" / "sharing" / "src" / "main" / "AndroidManifest.xml").is_file()
    assert (dest / "pyxpo-gen" / "jniLibs" / "arm64-v8a" / "libpython3.13.so").is_file()
    for p in dest.rglob("*"):
        if p.is_file() and p.suffix in (".kts", ".xml", ".kt"):
            assert not re.search(r"\{\{\w+\}\}", p.read_text()), p
            if "pyxpo-gen" not in p.parts:
                assert str(tmp_path) not in p.read_text(), p
