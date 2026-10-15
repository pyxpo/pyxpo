import plistlib
import xml.etree.ElementTree as ET

import pytest

from pyxpo import config_plugins as cp
from pyxpo import native_config
from pyxpo.app_config import ConfigError
from pyxpo.build import android_config, autolink, ios_config

PLUGIN = '''
from pyxpo.config_plugins import *

def plugin(config, props):
    with_info_plist(config, lambda p: p.update({"MyKey": props.get("v", "x")}))
    with_entitlements(config, lambda e: e.update({"com.apple.security.application-groups": ["group.a"]}))
    with_xcconfig(config, lambda x: x.update({"OTHER_LDFLAGS": "-ObjC", "IPHONEOS_DEPLOYMENT_TARGET": "17.0"}))
    def manifest(root):
        app = root.find("application")
        ET.SubElement(root, "uses-feature", {android_name("name"): "android.hardware.camera", android_name("required"): "false"})
        app.set(android_name("largeHeap"), "true")
    with_android_manifest(config, manifest)
    with_gradle_properties(config, lambda d: d.update({"org.gradle.jvmargs": "-Xmx3g"}))
    with_app_gradle(config, lambda l: l.append("android.packagingOptions.jniLibs.useLegacyPackaging = true"))
    with_android_res_values(config, lambda d: d.update({"hello": ("string", "it's \\"ok\\" & <b>"), "on": ("bool", True)}))
    with_dangerous_mod(config, "ios", lambda c: (c.native / "ios-ran").write_text(c.platform))
    with_dangerous_mod(config, "android", lambda c: (c.native / "android-ran").write_text(c.platform))
    return config
'''.replace("from pyxpo.config_plugins import *", "import xml.etree.ElementTree as ET\nfrom pyxpo.config_plugins import *")


def _nc(project, plugins):
    return native_config.resolve({"name": "Demo", "bundle_id": "dev.x.demo", "plugins": plugins}, project)


def _proj(tmp_path, src=PLUGIN, name="p.py"):
    (tmp_path / name).write_text(src)
    return tmp_path


def test_load_file_plugin_with_props(tmp_path):
    p = _proj(tmp_path)
    mods = cp.load(_nc(p, [["./p.py", {"v": "hi"}]]), p)
    assert not mods.empty()
    assert mods.apply_info_plist({})["MyKey"] == "hi"
    assert mods.apply_xcconfig({})["OTHER_LDFLAGS"] == "-ObjC"


def test_load_module_and_named_function(tmp_path):
    _proj(tmp_path, "from pyxpo.config_plugins import with_info_plist\ndef other(c, p):\n    with_info_plist(c, lambda d: d.update(A=1))\n", "myplug.py")
    mods = cp.load(_nc(tmp_path, ["myplug:other"]), tmp_path)
    assert mods.apply_info_plist({}) == {"A": 1}


def test_no_plugins_is_empty(tmp_path):
    assert cp.load(_nc(tmp_path, []), tmp_path).empty()
    assert cp.load(_nc(tmp_path, ["x"]), None).empty()


@pytest.mark.parametrize("entry,msg", [
    ("./missing.py", "file not found"),
    ("no_such_module_xyz", "cannot import"),
    ("./p.py:nope", "no function"),
])
def test_load_errors(tmp_path, entry, msg):
    p = _proj(tmp_path)
    with pytest.raises(ConfigError, match=msg):
        cp.load(_nc(p, [entry]), p)


def test_plugin_exception_and_bad_return_are_config_errors(tmp_path):
    _proj(tmp_path, "def plugin(c, p):\n    raise ValueError('boom')\n", "bad.py")
    _proj(tmp_path, "def plugin(c, p):\n    return 5\n", "ret.py")
    with pytest.raises(ConfigError, match="bad.py.*ValueError: boom"):
        cp.load(_nc(tmp_path, ["./bad.py"]), tmp_path)
    with pytest.raises(ConfigError, match="must return"):
        cp.load(_nc(tmp_path, ["./ret.py"]), tmp_path)


def test_plugin_cannot_change_native_config(tmp_path):
    _proj(tmp_path, "def plugin(c, p):\n    c.native['name'] = 'Evil'\n", "mut.py")
    nc = _nc(tmp_path, ["./mut.py"])
    cp.load(nc, tmp_path)
    assert nc["name"] == "Demo"


def test_mod_may_return_replacement(tmp_path):
    cfg = cp.PluginConfig({}, tmp_path, cp.Mods())
    cp.with_info_plist(cfg, lambda d: {"new": 1})
    assert cfg.mods.apply_info_plist({"old": 1}) == {"new": 1}
    with pytest.raises(ConfigError):
        cp.with_info_plist(cfg, "nope")
    with pytest.raises(ConfigError):
        cp.with_dangerous_mod(cfg, "web", lambda c: None)


def test_ios_files(tmp_path):
    p = _proj(tmp_path)
    nc = _nc(p, ["./p.py"])
    mods = cp.load(nc, p)
    gen = tmp_path / "gen"
    gen.mkdir()
    assert ios_config.write(gen, tmp_path / "native", nc, mods) is True
    assert plistlib.loads((gen / "Info.plist").read_bytes())["MyKey"] == "x"
    assert plistlib.loads((gen / "App.entitlements").read_bytes())["com.apple.security.application-groups"] == ["group.a"]
    lines = ios_config.xcconfig_lines(nc, True, mods.apply_xcconfig({}))
    assert lines[-1].startswith("IPHONEOS_DEPLOYMENT_TARGET = 17.0") or lines[-2].startswith("IPHONEOS_DEPLOYMENT_TARGET = 17.0")
    assert lines.index("IPHONEOS_DEPLOYMENT_TARGET = 15.0") < lines.index("IPHONEOS_DEPLOYMENT_TARGET = 17.0")  # plugin line is last


def test_android_files(tmp_path):
    p = _proj(tmp_path)
    nc = _nc(p, ["./p.py"])
    mods = cp.load(nc, p)
    gen = tmp_path / "gen"
    android_config.write(gen, nc, p, mods)
    for kind in ("debug", "release"):
        text = (gen / "manifest" / kind / "AndroidManifest.xml").read_text()
        root = ET.fromstring(text)
        assert text.startswith('<?xml') and "Generated by pyxpo" in text
        assert root.find("application").get(cp.android_name("largeHeap")) == "true"
        assert root.find("uses-feature").get(cp.android_name("required")) == "false"
        assert root.find("application").get(cp.tools_name("replace"))  # tools:replace survives the round trip
        assert "xmlns:tools" in text and "android:allowBackup" in text
    assert "useLegacyPackaging = true" in (gen / "pyxpo.app.gradle").read_text()
    assert 'main.res.srcDir "${rootDir}/pyxpo-gen/res"' in (gen / "pyxpo.app.gradle").read_text()
    res = ET.fromstring((gen / "res" / "values" / "pyxpo_plugins.xml").read_text())
    vals = {e.get("name"): (e.tag, e.text) for e in res}
    assert vals["on"] == ("bool", "true")
    assert vals["hello"] == ("string", "it\\'s \\\"ok\\\" & <b>")


def test_res_values_type_checked():
    with pytest.raises(ConfigError, match="type must be"):
        cp.res_values_xml({"a": ("float", "1")})


def test_gradle_properties_block_is_idempotent_and_keeps_user_lines(tmp_path):
    p = _proj(tmp_path)
    mods = cp.load(_nc(p, ["./p.py"]), p)
    native = tmp_path / "android"
    native.mkdir()
    (native / "gradle.properties").write_text("android.useAndroidX=true\n")
    android_config.write_gradle_properties(native, mods)
    first = (native / "gradle.properties").read_text()
    android_config.write_gradle_properties(native, mods)
    assert (native / "gradle.properties").read_text() == first
    assert first.startswith("android.useAndroidX=true\n") and "org.gradle.jvmargs=-Xmx3g" in first and first.count(android_config.MARK_BEGIN) == 1
    android_config.write_gradle_properties(native, cp.Mods())  # plugin removed: block goes, user lines stay
    assert (native / "gradle.properties").read_text() == "android.useAndroidX=true\n"


def test_gradle_properties_not_created_without_mods(tmp_path):
    android_config.write_gradle_properties(tmp_path, cp.Mods())
    assert not (tmp_path / "gradle.properties").exists()


def test_dangerous_mods_run_per_platform(tmp_path):
    p = _proj(tmp_path)
    mods = cp.load(_nc(p, ["./p.py"]), p)
    mods.run_dangerous("ios", p, tmp_path)
    assert (tmp_path / "ios-ran").read_text() == "ios" and not (tmp_path / "android-ran").exists()


def test_module_option_false_drops_info_plist_key():
    class M:
        name = "image-picker"
        ios = {"infoPlist": {"NSMicrophoneUsageDescription": {"default": "mic", "option": "microphoneUsage"},
                             "NSCameraUsageDescription": {"default": "cam", "option": "cameraUsage"}}}
    assert set(autolink.info_plist([M()], {})) == {"NSMicrophoneUsageDescription", "NSCameraUsageDescription"}
    out = autolink.info_plist([M()], {"image-picker": {"infoPlist": {"NSMicrophoneUsageDescription": False}}})
    assert out == {"NSCameraUsageDescription": "cam"}
