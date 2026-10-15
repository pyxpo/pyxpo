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
