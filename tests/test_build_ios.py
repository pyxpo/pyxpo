import importlib
import pytest
import os
import plistlib
import re
import subprocess
import sys
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
    (b / "Frameworks" / "Python.framework").mkdir()
    assert ios_wrap.prune(str(b)) == [] and fw.is_dir()
    (ext.parent / "_c.cpython-313-iphoneos.fwork").unlink()  # the module left the app; its framework stayed
    assert ios_wrap.prune(str(b)) == [str(fw)] and not fw.exists()
    assert (b / "Frameworks" / "Python.framework").is_dir()


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
    ran = []
    monkeypatch.setattr(ios, "_run", lambda cmd, **k: ran.append([str(c) for c in cmd]))
    monkeypatch.setattr(ios.shutil, "which", lambda name: "/usr/bin/" + name)
    dest = ios.prebuild(proj)
    assert dest == proj / "ios"
    assert ran[0][:2] == ["xcodegen", "generate"]  # the .xcodeproj exists right after prebuild, as in Expo
    assert "preBuildScripts" in (dest / "project.yml").read_text()
    assert (dest / "project.yml").is_file() and (dest / "App" / "AppDelegate.swift").is_file()
    assert (dest / "pyxpo-gen" / "native" / "pyxpo_bridge.c").is_file()
    xc = (dest / "pyxpo-gen" / "Pyxpo.xcconfig").read_text()
    for line in ("PRODUCT_BUNDLE_IDENTIFIER = dev.x.demo", "PYXPO_DISPLAY_NAME = Demo App", "MARKETING_VERSION = 2.3.4",
                 "DEVELOPMENT_TEAM = ABCDE12345", "PYXPO_SCHEME = dev.x.demo", "PYXPO_PYTHON = " + sys.executable):
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


def test_adhoc_catalyst_build_runs_from_finder(tmp_path, monkeypatch):
    # An ad-hoc signed app with hardened runtime is killed at launch: library validation rejects Python.framework.
    _fake_dist(tmp_path, monkeypatch)
    ran = []
    monkeypatch.setattr(ios, "_run", lambda cmd, **k: ran.append([str(c) for c in cmd]))
    monkeypatch.setattr(ios.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(ios, "stage", lambda *a, **k: None)
    proj = _project(tmp_path)
    with pytest.raises(ios.BuildError, match="app not produced"):
        ios.build(proj, release=True, kind="catalyst")
    xcb = [c for c in ran if c[0] == "xcodebuild"][0]
    assert "Release" in xcb and "CODE_SIGN_IDENTITY=-" in xcb and "ENABLE_HARDENED_RUNTIME=NO" in xcb
    ran.clear()
    with pytest.raises(ios.BuildError):
        ios.build(_project(tmp_path / "team", '[tool.pyxpo.ios]\nteam_id = "ABCDE12345"\n'), release=True,
                  kind="catalyst")
    xcb = [c for c in ran if c[0] == "xcodebuild"][0]
    assert "ENABLE_HARDENED_RUNTIME=NO" not in xcb  # signed with a team: hardened runtime stays for notarizing


def test_include_ships_more_package_folders(tmp_path, monkeypatch):
    from pyxpo.config import app_dirs
    _fake_dist(tmp_path, monkeypatch)
    monkeypatch.setattr(ios, "_run", lambda *a, **k: None)
    proj = _project(tmp_path, 'include = ["corelib"]\n')
    (proj / "corelib").mkdir()
    (proj / "corelib" / "__init__.py").write_text("y = 2\n")
    (proj / "corelib" / ".secret").write_text("no")
    (proj / "tools").mkdir()
    (proj / "tools" / "x.py").write_text("")
    native = ios.prebuild(proj)
    ios.stage(native, proj, ios.load_config(proj), False, "simulator")
    root = native / "pyxpo-gen" / "stage" / "app_root"
    assert (root / "corelib" / "__init__.py").is_file() and (root / "app" / "index.py").is_file()
    assert not (root / "corelib" / ".secret").exists() and not (root / "tools").exists()
    for bad in (["../x"], ["app"], ["a/b"]):
        with pytest.raises(ValueError, match="not a top-level package"):
            app_dirs({"include": bad}, proj)
    with pytest.raises(FileNotFoundError, match="no folder 'gone'"):
        app_dirs({"include": ["gone"]}, proj)


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
    assert "python=" in props
    # `cd android && ./gradlew assembleRelease` works after prebuild, as after `expo prebuild`
    assert os.access(str(dest / "gradlew"), os.X_OK) and (dest / "gradle" / "wrapper" / "gradle-wrapper.jar").is_file()
    assert "gradle-8.10.2" in (dest / "gradle" / "wrapper" / "gradle-wrapper.properties").read_text()
    assert "pyxpoStage" in (dest / "app" / "build.gradle.kts").read_text()
    monkeypatch.setattr(droid.runtime, "is_dev_checkout", lambda: False)
    assert droid.find_gradle(dest) == str(dest / "gradlew")
    gradle = dest / "app" / "build.gradle.kts"
    gradle.write_text("// mine\n")  # an old ejected project without the native-module line
    with pytest.raises(droid.BuildError, match="native-module line"):
        droid.stage(dest, proj, droid.load_config(proj), False, ["arm64-v8a"])
    gradle.write_text('// mine\napply(from = "../pyxpo-gen/modules.app.gradle.kts")\n')
    droid.stage(dest, proj, droid.load_config(proj), False, ["arm64-v8a"])
    assert gradle.read_text().startswith("// mine\n")
    names = zipfile.ZipFile(str(dest / "pyxpo-gen" / "app-debug" / "pyxpo" / "app.zip")).namelist()
    assert "pyxpo_sharing/__init__.py" in names and "pyxpo/modules.py" in names
    assert not [n for n in names if (n.startswith("pyxpo_image_manipulator/") or n.endswith((".kt", ".swift", ".json"))) and n != "pyxpo/_app_config.json"]
    assert (dest / "pyxpo-gen" / "modules" / "sharing" / "src" / "main" / "AndroidManifest.xml").is_file()
    assert (dest / "pyxpo-gen" / "jniLibs" / "arm64-v8a" / "libpython3.13.so").is_file()
    for p in dest.rglob("*"):
        if p.is_file() and p.suffix in (".kts", ".xml", ".kt"):
            assert not re.search(r"\{\{\w+\}\}", p.read_text()), p
            if "pyxpo-gen" not in p.parts:
                assert str(tmp_path) not in p.read_text(), p


def test_sync_tree_rewrites_only_changes_and_keeps_build_outputs(tmp_path):
    pb = importlib.import_module("pyxpo.build.prebuild")
    dst, src = tmp_path / "gen", tmp_path / "gen.tmp"
    for d, files in ((dst, {"same.txt": "a", "changed.txt": "old", "stale.txt": "x", "sub/stale/f": "x",
                             "module-api/build/out.jar": "jar", "stage/app.py": "kept"}),
                     (src, {"same.txt": "a", "changed.txt": "new", "sub/new.txt": "n", "module-api/build.gradle.kts": "k"})):
        for rel, text in files.items():
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_text(text)
    os.symlink(str(tmp_path), str(src / "link"))
    os.utime(str(dst / "same.txt"), (1, 1))
    pb.sync_tree(src, dst, keep=("stage",))
    assert not src.exists()
    assert (dst / "same.txt").stat().st_mtime == 1  # unchanged files keep their mtime (no needless rebuilds)
    assert (dst / "changed.txt").read_text() == "new" and (dst / "sub" / "new.txt").is_file()
    assert not (dst / "stale.txt").exists() and not (dst / "sub" / "stale").exists()
    assert (dst / "module-api" / "build" / "out.jar").is_file() and (dst / "stage" / "app.py").is_file()
    assert os.readlink(str(dst / "link")) == str(tmp_path)


def test_prune_site_drops_what_the_app_store_refuses(tmp_path):
    from pyxpo.build import ios
    site = tmp_path / "site"
    for rel in ("numpy/_core/lib/libnpymath.a", "numpy/random/lib/libnpyrandom.a", "bin/f2py", "x/y.o",
                "numpy/__init__.py", "numpy/_core/_multiarray_umath.cpython-313-iphoneos.so", "numpy/_core/lib/pkgconfig/npymath.pc"):
        (site / rel).parent.mkdir(parents=True, exist_ok=True)
        (site / rel).write_text("x")
    ios.prune_site(site)
    left = sorted(str(p.relative_to(site)) for p in site.rglob("*") if p.is_file())
    assert left == ["numpy/__init__.py", "numpy/_core/_multiarray_umath.cpython-313-iphoneos.so",
                    "numpy/_core/lib/pkgconfig/npymath.pc"]


def test_runtime_starts_python_in_utf8_mode():
    # Apps started from Finder have no LANG; without UTF-8 mode subprocess text and open() fall back to ASCII.
    src = (Path(__file__).parent.parent / "src/pyxpo/templates/ios/gen/runtime/PyxpoRuntime.m").read_text()
    pre = src.index("preconfig.utf8_mode = 1;")
    assert src.index("Py_PreInitialize(&preconfig)") > pre
    assert src.index("Py_InitializeFromConfig(&config)") > pre


def test_pick_simulator_by_name_or_udid():
    data = {"devices": {
        "com.apple.CoreSimulator.SimRuntime.iOS-27-0": [
            {"name": "iPhone 18", "udid": "B", "state": "Booted"},
            {"name": "iPad Pro", "udid": "P", "state": "Shutdown"}],
    }}
    assert ios.pick_simulator(data, "iPad Pro")["udid"] == "P"
    assert ios.pick_simulator(data, "P")["udid"] == "P"
    assert ios.pick_simulator(data, "iPhone 99") is None


def test_show_simulator_falls_back_to_devicehub(monkeypatch):
    # Xcode 27 has no Simulator.app; DeviceHub shows simulators instead.
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd[2])
        return subprocess.CompletedProcess(cmd, 0 if cmd[2] == "com.apple.dt.Devices" else 1)

    monkeypatch.setattr(ios.subprocess, "run", fake_run)
    assert ios.show_simulator("U") is True
    assert calls == ["com.apple.iphonesimulator", "com.apple.dt.Devices"]


def test_compile_pyc_ships_bytecode(tmp_path):
    app = tmp_path / "app_root" / "app"
    app.mkdir(parents=True)
    (app / "main.py").write_text("X = 1\n")
    ios.compile_pyc([tmp_path / "app_root", tmp_path / "missing"], Path(sys.executable))
    pyc = list((app / "__pycache__").glob("main.*.pyc"))
    assert pyc and pyc[0].read_bytes()[4:8] == b"\x03\x00\x00\x00"  # checked-hash flags
    ios.compile_pyc([tmp_path / "app_root"], None)  # no host Python: no-op


def _fake_stdlib(tmp_path):
    from pyxpo.build import ios
    lib = tmp_path / "lib" / "python3.13"
    for mod in ("os", "json/__init__"):
        py = lib / (mod + ".py")
        py.parent.mkdir(parents=True, exist_ok=True)
        py.write_text("x = 1\n")
        cache = py.parent / "__pycache__"
        cache.mkdir(exist_ok=True)
        stem = py.stem
        for tag in ("", ".opt-1", ".opt-2"):
            (cache / ("%s.cpython-313%s.pyc" % (stem, tag))).write_bytes(b"pyc")
    (lib / "nopyc.py").write_text("y = 2\n")
    return ios, lib


def test_slim_stdlib_debug_drops_optimized_pyc_only(tmp_path):
    ios, lib = _fake_stdlib(tmp_path)
    ios.slim_stdlib(lib, release=False)
    assert not list(lib.rglob("*.opt-*.pyc"))
    assert (lib / "os.py").is_file() and (lib / "__pycache__" / "os.cpython-313.pyc").is_file()


def test_slim_stdlib_release_ships_sourceless_pyc(tmp_path):
    ios, lib = _fake_stdlib(tmp_path)
    ios.slim_stdlib(lib, release=True)
    assert (lib / "os.pyc").is_file() and not (lib / "os.py").exists()
    assert (lib / "json" / "__init__.pyc").is_file() and not (lib / "json" / "__init__.py").exists()
    assert (lib / "nopyc.py").is_file()  # no compiled copy: the source stays
    assert not list(lib.rglob("__pycache__"))


def test_ios_stdlib_skips_interactive_only_packages():
    from pyxpo.build import ios
    assert {"pydoc_data", "_pyrepl", "test", "idlelib"} <= set(ios.IOS_STDLIB_SKIP)


def test_ios_stdlib_skips_test_extensions():
    from pyxpo.build import ios
    names = ["_testcapi.cpython-313-iphonesimulator.so", "xxlimited_35.cpython-313-iphonesimulator.so",
             "_ctypes.cpython-313-iphonesimulator.so", "_ssl.cpython-313-iphonesimulator.so", "pydoc_data", "json"]
    assert ios._skip_stdlib(names) == names[:2] + ["pydoc_data"]
