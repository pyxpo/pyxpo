import json
from pathlib import Path

import pytest

from pyxpo import app_config, native_config
from pyxpo.app_config import ConfigError, colors, images
from pyxpo.config import load_config


def project(tmp_path, body, extra=""):
    (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\nversion="2.0.0"\n[tool.pyxpo]\n%s\n' % body + extra)
    return tmp_path


def test_defaults_match_legacy(tmp_path):
    p = project(tmp_path, 'name = "My App"\nbundle_id = "com.acme.app"')
    r = native_config.resolve(load_config(p), p)
    assert (r["name"], r["product_name"], r["version"], r["build_number"], r["scheme"]) == ("My App", "MyApp", "2.0.0", 1, "com.acme.app")
    assert r["ios"]["bundle_id"] == r["android"]["package"] == "com.acme.app"
    assert r["ios"]["supports_tablet"] is True and r["android"]["min_sdk"] == 24


def test_nested_tables_and_camel_case(tmp_path):
    p = project(tmp_path, 'name = "A"\nuserInterfaceStyle = "dark"\nbuildNumber = 4',
                '[tool.pyxpo.android]\nversionCode = 9\npermissions = ["CAMERA"]\n[tool.pyxpo.ios]\nsupportsTablet = false\n')
    r = native_config.resolve(load_config(p), p)
    assert r["user_interface_style"] == "dark" and r["build_number"] == 4
    assert r["android"]["version_code"] == 9 and r["android"]["permissions"] == ["android.permission.CAMERA"]
    assert r["ios"]["supports_tablet"] is False and r["ios"]["build_number"] == "4"


def test_both_spellings_rejected(tmp_path):
    p = project(tmp_path, 'build_number = 1\nbuildNumber = 2')
    with pytest.raises(ConfigError, match="both"):
        load_config(p)


def test_unknown_key_suggests(tmp_path):
    p = project(tmp_path, 'name = "A"\nbundel_id = "com.a.b"')
    with pytest.raises(ConfigError, match="did you mean 'bundle_id'"):
        load_config(p)


@pytest.mark.parametrize("body,needle", [
    ('orientation = "sideways"', "expected one of default, portrait, landscape"),
    ('background_color = "red"', "expected a color"),
    ('bundle_id = "nodots"', "reverse-DNS"),
    ('icon = "a.jpg"', "expected a .png path"),
])
def test_value_errors_name_key(tmp_path, body, needle):
    with pytest.raises(ConfigError, match=needle):
        load_config(project(tmp_path, body))


def test_android_min_sdk_and_ios_target_range(tmp_path):
    with pytest.raises(ConfigError, match=r"min_sdk: expected an integer >= 24"):
        load_config(project(tmp_path, "", "[tool.pyxpo.android]\nmin_sdk = 21\n"))
    with pytest.raises(ConfigError, match="deployment_target: expected >= 15.0"):
        load_config(project(tmp_path, "", '[tool.pyxpo.ios]\ndeployment_target = "14.0"\n'))


def test_dynamic_config(tmp_path):
    p = project(tmp_path, 'name = "A"\nbundle_id = "com.a.b"')
    (p / "app_config.py").write_text('def config(cfg):\n    cfg["bundle_id"] += ".dev"\n    return cfg\n')
    assert load_config(p)["bundle_id"] == "com.a.b.dev"


def test_asset_checks(tmp_path):
    p = project(tmp_path, 'icon = "icon.png"')
    with pytest.raises(ConfigError, match="file not found"):
        app_config.check_assets(native_config.resolve(load_config(p), p), p, {})
    (p / "icon.png").write_bytes(images.solid_png(512, 512))
    with pytest.raises(ConfigError, match="at least 1024"):
        app_config.check_assets(native_config.resolve(load_config(p), p), p, {})
    (p / "icon.png").write_bytes(images.solid_png(1024, 1024, (1, 2, 3, 128)))
    w = app_config.check_assets(native_config.resolve(load_config(p), p), p, {})
    assert any("alpha" in x for x in w)
    (p / "icon.png").write_bytes(images.solid_png(1024, 1024, (1, 2, 3, 255), alpha=False))
    assert app_config.check_assets(native_config.resolve(load_config(p), p), p, {}) == []


def test_secret_warning(tmp_path):
    p = project(tmp_path, "", '[tool.pyxpo.extra]\napi_token = "x"\n')
    assert any("secret" in w for w in app_config.check_assets(native_config.resolve(load_config(p), p), p, {}))


def test_png_alpha_detection():
    opaque = images.solid_png(4, 4, (9, 9, 9, 255))
    clear = images.solid_png(4, 4, (9, 9, 9, 0))
    for data, expect in ((opaque, False), (clear, True)):
        f = Path(__import__("tempfile").mkdtemp()) / "a.png"
        f.write_bytes(data)
        i = images.info(f)
        assert (i["width"], i["height"], i["has_alpha"]) == (4, 4, expect)


def test_colors():
    assert colors.android_argb("#11223380") == "#80112233"
    assert colors.android_argb("#fff") == "#ffffffff"
    assert colors.components("#ff0000")["red"] == "1.000"
    assert colors.is_dark("#000") and not colors.is_dark("#fff")


def test_json_schema_valid():
    s = app_config.json_schema()
    json.dumps(s)
    assert "splash" in s["properties"] and s["properties"]["orientation"]["enum"]


def test_ios_plist_entitlements_xcconfig(tmp_path):
    import plistlib

    from pyxpo.build import ios_config
    p = project(tmp_path, 'name = "A"\nscheme = ["a", "b"]\norientation = "landscape"\nuser_interface_style = "dark"',
                '[tool.pyxpo.ios]\nsupports_tablet = false\nassociated_domains = ["applinks:acme.com"]\n'
                'config = { uses_non_exempt_encryption = false }\ninfo_plist = { NSCameraUsageDescription = "scan", LSApplicationQueriesSchemes = ["x"] }\n')
    nc = native_config.resolve(load_config(p), p)
    from pyxpo.build import ios
    base = plistlib.loads((ios.TEMPLATE / "user" / "App" / "Info.plist").read_bytes())
    pl = ios_config.info_plist(base, nc)
    assert pl["CFBundleURLTypes"][0]["CFBundleURLSchemes"] == ["a", "b"] and len(pl["CFBundleURLTypes"]) == 1
    assert pl["UISupportedInterfaceOrientations"] == ios_config.LANDSCAPE and "UISupportedInterfaceOrientations~ipad" not in pl
    assert pl["UIUserInterfaceStyle"] == "Dark" and pl["ITSAppUsesNonExemptEncryption"] is False
    assert pl["NSCameraUsageDescription"] == "scan" and pl["LSApplicationQueriesSchemes"] == ["x"]
    assert ios_config.entitlements(nc) == {"com.apple.developer.associated-domains": ["applinks:acme.com"]}
    xc = ios_config.xcconfig_lines(nc, True)
    assert "PYXPO_DEVICE_FAMILY = 1" in xc and "CODE_SIGN_ENTITLEMENTS = pyxpo-gen/App.entitlements" in xc


def test_android_manifest_and_gradle(tmp_path):
    import xml.etree.ElementTree as ET

    from pyxpo.build import android_config
    p = project(tmp_path, 'name = "A"\nscheme = ["a", "b"]\norientation = "portrait"',
                '[tool.pyxpo.android]\nmin_sdk = 26\npermissions = ["CAMERA"]\nblocked_permissions = ["VIBRATE"]\n'
                'software_keyboard_layout_mode = "pan"\npredictive_back_gesture_enabled = true\n'
                'intent_filters = [{ action = "VIEW", autoVerify = true, data = [{ scheme = "https", host = "a.com" }], category = ["BROWSABLE"] }]\n')
    nc = native_config.resolve(load_config(p), p)
    dbg, rel = android_config.manifest(nc, True), android_config.manifest(nc, False)
    ET.fromstring(dbg)  # well-formed
    assert 'android:usesCleartextTraffic="true"' in dbg and 'android:usesCleartextTraffic="false"' in rel
    assert 'android.permission.CAMERA' in dbg and 'tools:node="remove"' in dbg and 'android:screenOrientation="portrait"' in dbg
    assert 'adjustPan' in dbg and 'enableOnBackInvokedCallback' in dbg and 'android:autoVerify="true"' in dbg
    assert dbg.count('android:scheme="a"') == 1 and 'android:host="a.com"' in dbg
    assert "minSdk 26" in android_config.gradle(nc)
    android_config.write(tmp_path / "gen", nc, tmp_path)
    assert (tmp_path / "gen" / "manifest" / "release" / "AndroidManifest.xml").is_file()


def _icon_project(tmp_path, ios="", android=""):
    for n, px in (("l.png", 1024), ("d.png", 1024), ("t.png", 512), ("fg.png", 432), ("mono.png", 432)):
        (tmp_path / n).write_bytes(images.solid_png(px, px, (200, 30, 60, 255)))
    p = project(tmp_path, 'name = "A"', ios + android)
    return p, native_config.resolve(load_config(p), p)


def test_icons_ios(tmp_path):
    from pyxpo.build import icons
    p, nc = _icon_project(tmp_path, '[tool.pyxpo.ios]\nicon = { light = "l.png", dark = "d.png", tinted = "t.png" }\n')
    gen = tmp_path / "gen"
    assert icons.ios(p, nc, gen) is True
    d = gen / "runtime/Resources/Assets.xcassets/AppIcon.appiconset"
    c = json.loads((d / "Contents.json").read_text())["images"]
    assert [e.get("appearances", [{}])[0].get("value") for e in c] == [None, "dark", "tinted"]
    assert all(images.info(d / e["filename"])["width"] == 1024 for e in c)  # 512 tinted was scaled up
    nc["ios"]["icon"] = {}
    # No icon: an empty AppIcon set, so the platform default icon stays and actool finds the set XcodeGen names.
    assert icons.ios(p, nc, tmp_path / "gen2") is False
    empty = json.loads((tmp_path / "gen2/runtime/Resources/Assets.xcassets/AppIcon.appiconset/Contents.json").read_text())
    assert [i.get("filename") for i in empty["images"]] == [None]


def test_icons_android(tmp_path):
    from pyxpo.build import android_config, icons
    p, nc = _icon_project(tmp_path, android='[tool.pyxpo.android]\nadaptive_icon = { foreground_image = "fg.png", background_color = "#112233", monochrome_image = "mono.png" }\n')
    gen = tmp_path / "gen"
    assert icons.android(p, nc, gen) is True
    res = gen / "res"
    for dpi, px in icons.LEGACY_DPI.items():
        assert images.info(res / ("mipmap-%s/ic_launcher.png" % dpi))["width"] == px
    xml = (res / "mipmap-anydpi-v26/ic_launcher.xml").read_text()
    assert "@color/ic_launcher_background" in xml and "monochrome" in xml
    assert "#ff112233" in (res / "values/ic_launcher_background.xml").read_text()
    assert 'android:icon="@mipmap/ic_launcher"' in android_config.manifest(nc, True, True)
    assert "pyxpo-gen/res" in android_config.gradle(nc, True)
    nc["android"]["adaptive_icon"] = {}
    assert icons.android(p, nc, tmp_path / "gen2") is False


def test_android_meta_data_and_ios_plist_bars(tmp_path):
    from pyxpo.build import android_config, ios, ios_config
    import plistlib
    p = project(tmp_path, 'background_color = "#336699"\nuser_interface_style = "dark"',
                '[tool.pyxpo.status_bar]\nstyle = "light"\nhidden = true\n[tool.pyxpo.navigation_bar]\nstyle = "dark"\n')
    nc = native_config.resolve(load_config(p), p)
    m = android_config.manifest(nc, False)
    for frag in ('"pyxpo.background_color" android:value="argb:ff336699"', '"pyxpo.user_interface_style" android:value="dark"',
                 '"pyxpo.status_bar_style" android:value="light"', '"pyxpo.status_bar_hidden" android:value="true"',
                 '"pyxpo.navigation_bar_style" android:value="dark"', '"pyxpo.navigation_bar_hidden" android:value="false"'):
        assert frag in m
    base = plistlib.loads((ios.TEMPLATE / "user" / "App" / "Info.plist").read_bytes())
    pl = ios_config.info_plist(base, nc)
    assert pl["PyxpoBackgroundColor"] == "#336699" and pl["PyxpoStatusBarStyle"] == "light" and pl["PyxpoStatusBarHidden"] is True
    assert pl["UIStatusBarHidden"] is True
    nc["status_bar"]["hidden"] = False
    assert "UIStatusBarHidden" not in ios_config.info_plist(dict(pl), nc)


def test_splash_ios_and_android(tmp_path):
    import plistlib
    from pyxpo.build import android_config, ios_config, splash
    p, nc = _icon_project(tmp_path, '[tool.pyxpo.splash]\nimage = "l.png"\nimage_width = 100\nbackground_color = "#112233"\n'
                          '[tool.pyxpo.splash.dark]\nimage = "d.png"\nbackground_color = "#000000"\n')
    gen = tmp_path / "gen"
    assert splash.ios(p, nc, gen) is True
    cat = gen / "runtime/Resources/Assets.xcassets"
    cs = json.loads((cat / "SplashBackground.colorset/Contents.json").read_text())["colors"]
    assert [c.get("appearances", [{}])[0].get("value") for c in cs] == [None, "dark"]
    assert cs[0]["color"]["components"]["red"] == "0.067"
    im = cat / "SplashImage.imageset"
    assert images.info(im / "splash-light.png")["width"] == 300  # 100pt @3x
    assert json.loads((im / "Contents.json").read_text())["images"][1]["appearances"][0]["value"] == "dark"
    pl = ios_config.info_plist({}, nc)
    assert pl["UILaunchScreen"] == {"UIColorName": "SplashBackground", "UIImageName": "SplashImage"}
    # no image: color only, stale imageset removed
    nc["ios"]["splash"]["image"] = None
    assert splash.ios(p, nc, gen) is False and not im.exists()
    assert ios_config.info_plist({}, nc)["UILaunchScreen"] == {"UIColorName": "SplashBackground"}

    agen = tmp_path / "agen"
    assert splash.android(p, nc, agen)["theme"] is True
    res = agen / "res"
    assert "#ff112233" in (res / "values/pyxpo_splash_bg.xml").read_text()
    assert "#ff000000" in (res / "values-night/pyxpo_splash_bg.xml").read_text()
    assert "windowSplashScreenBackground" in (res / "values-v31/pyxpo_splash_theme.xml").read_text()
    assert "windowSplashScreenAnimatedIcon" in (res / "values-v31/pyxpo_splash_theme.xml").read_text()
    assert (res / "drawable-night-nodpi/pyxpo_splash_image.png").is_file()
    win = (res / "drawable/pyxpo_splash_window.xml").read_text()
    assert 'android:width="100dp"' in win and 'android:height="100dp"' in win
    m = android_config.manifest(nc, False, False, True)
    assert 'android:theme="@style/PyxpoSplash"' in m and "android:theme" in m.split("tools:replace=")[-1]
    assert '"pyxpo.splash_image_width" android:value="100"' in m


def test_constants_app_json(tmp_path, monkeypatch):
    import json
    from pyxpo.apis import constants
    from pyxpo.build import app_json
    nc = native_config.resolve({"name": "Demo", "version": "2.3.4", "build_number": 7, "extra": {"api": "x"},
                                "ios": {"team_id": "TEAM123"}, "android": {"keystore": "k.jks"}}, tmp_path)
    app_json.write(tmp_path, nc)
    data = json.loads((tmp_path / "_app_config.json").read_text())
    assert data["version"] == "2.3.4" and data["extra"] == {"api": "x"} and data["android"]["version_code"] == 7
    assert "TEAM123" not in json.dumps(data) and "k.jks" not in json.dumps(data)
    monkeypatch.setattr(constants, "_cache", data)
    C = constants.Constants
    assert C.native_app_version == C.nativeAppVersion == "2.3.4"
    assert C.expo_config["name"] == "Demo" and C.extra == {"api": "x"}
    assert C.execution_environment == "bare" and C.session_id == C.sessionId
    C.extra["api"] = "mutated"
    assert C.extra == {"api": "x"}
    monkeypatch.setattr(constants, "_cache", {})
    assert C.native_app_version is None and C.native_build_version is None and C.execution_environment == "unknown"


def test_android_build_properties(tmp_path):
    from pyxpo.build import android_config
    p = project(tmp_path, 'name = "A"',
                '[tool.pyxpo.build_properties.android]\nenable_minify_in_release_builds = true\nenable_shrink_resources_in_release_builds = true\n'
                'extra_proguard_rules = "-keep class com.acme.** { *; }"\n'
                'packaging_options = { pick_first = ["**/libc++_shared.so"], exclude = ["META-INF/it\'s.txt"] }\n')
    nc = native_config.resolve(load_config(p), p)
    g = android_config.gradle(nc)
    assert "minifyEnabled true" in g and "shrinkResources true" in g and "proguard-pyxpo.pro" in g
    assert "resources.pickFirsts.add('**/libc++_shared.so')" in g and "it\\'s.txt" in g
    android_config.write(tmp_path / "gen", nc, tmp_path)
    pro = (tmp_path / "gen" / "proguard-pyxpo.pro").read_text()
    assert "-keep class dev.pyxpo.**" in pro and "-keep class com.acme.**" in pro
    (tmp_path / "b").mkdir()
    q = project(tmp_path / "b", 'name = "B"')
    assert "minifyEnabled" not in android_config.gradle(native_config.resolve(load_config(q), q))
    (tmp_path / "c").mkdir()
    r = project(tmp_path / "c", 'name = "C"', '[tool.pyxpo.build_properties.android]\nenable_shrink_resources_in_release_builds = true\n')
    with pytest.raises(ConfigError, match="needs enable_minify"):
        native_config.resolve(load_config(r), r)


def test_ios_require_full_screen_without_base_orientations():
    from pyxpo.build import ios_config
    nc = native_config.resolve({"name": "A", "ios": {"require_full_screen": True}}, Path("."))
    p = ios_config.info_plist({}, nc)
    assert p["UIRequiresFullScreen"] is True and p["UISupportedInterfaceOrientations~ipad"] == ios_config.ALL_ORIENTATIONS


def test_mini_parse_reads_multi_line_arrays():
    """The no-tomli fallback reads an array split over lines (ISSUE 28) and still fails on a broken one."""
    from pyxpo.config import _mini_parse
    text = ('[tool.pyxpo]\nname = "x"\nmodules = ["whiteboard", "sqlite",\n           "image-picker"]\n'
            'icon = "a.png"\n[other]\nk = 1\n')
    assert _mini_parse(text) == {"name": "x", "modules": ["whiteboard", "sqlite", "image-picker"], "icon": "a.png"}
    with pytest.raises(ValueError):
        _mini_parse('[tool.pyxpo]\nmodules = ["a",\n')


def test_ios_ipad_gets_all_orientations_by_default():
    # The template is portrait-only for iPhone; App Store upload refuses an iPad app without all four.
    import plistlib

    from pyxpo.build import ios, ios_config
    base = plistlib.loads((ios.TEMPLATE / "user" / "App" / "Info.plist").read_bytes())
    p = ios_config.info_plist(base, native_config.resolve({"name": "A"}, Path(".")))
    assert p["UISupportedInterfaceOrientations"] == [ios_config.PORTRAIT]
    assert p["UISupportedInterfaceOrientations~ipad"] == ios_config.ALL_ORIENTATIONS
