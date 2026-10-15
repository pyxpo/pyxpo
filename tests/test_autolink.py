import json

import pytest

from pyxpo.build import autolink
from pyxpo.build.runtime import BuildError


def make_module(root, name="demo-mod", pkg="pyxpo_demo_mod", **extra):
    meta = {
        "name": name,
        "native": "Demo",
        "ios": {"classes": ["DemoModule"], "infoPlist": {"NSDemoUsageDescription": {"option": "demoText", "default": "Uses demo"}}},
        "android": {"namespace": "dev.pyxpo.modules.demo", "classes": ["dev.pyxpo.modules.demo.DemoModule"],
                    "dependencies": ["androidx.core:core-ktx:1.13.1"]},
    }
    meta.update(extra)
    d = root / name.replace("-", "_")
    (d / "ios").mkdir(parents=True)
    (d / "android" / "src" / "main").mkdir(parents=True)
    (d / "pyxpo-module.json").write_text(json.dumps(meta))
    (d / "ios" / "DemoModule.swift").write_text("final class DemoModule: PxModule {}\n")
    (d / "android" / "src" / "main" / "AndroidManifest.xml").write_text("<manifest/>")
    return autolink.Module(d, meta, pkg)


def test_validate_rejects_bad_meta():
    with pytest.raises(BuildError):
        autolink.validate({"name": "Bad Name", "native": "X"}, "f")
    with pytest.raises(BuildError):
        autolink.validate({"name": "ok", "native": "x"}, "f")
    with pytest.raises(BuildError):
        autolink.validate({"name": "ok", "native": "X", "android": {"classes": ["A"]}}, "f")
    with pytest.raises(BuildError):
        autolink.validate({"name": "ok", "native": "X", "ios": {"classes": []}}, "f")


def test_resolve_unknown_suggests(tmp_path):
    m = make_module(tmp_path)
    with pytest.raises(BuildError) as e:
        autolink.resolve({"modules": ["demo-mdo"]}, tmp_path, {m.name: m})
    assert "did you mean 'demo-mod'" in str(e.value)


def test_resolve_requires_listed_import(tmp_path):
    m = make_module(tmp_path / "mods")
    proj = tmp_path / "proj"
    (proj / "app").mkdir(parents=True)
    (proj / "app" / "index.py").write_text("x = 1\nfrom pyxpo_demo_mod import thing\n")
    with pytest.raises(BuildError) as e:
        autolink.resolve({"modules": []}, proj, {m.name: m})
    assert "app/index.py:2" in str(e.value) and "add 'demo-mod'" in str(e.value)
    assert autolink.resolve({"modules": ["demo-mod"]}, proj, {m.name: m}) == [m]


def test_resolve_dedupes_and_keeps_order(tmp_path):
    a, b = make_module(tmp_path, "aa", "pyxpo_aa"), make_module(tmp_path, "bb", "pyxpo_bb")
    out = autolink.resolve({"modules": ["bb", "aa", "bb"]}, tmp_path, {"aa": a, "bb": b})
    assert out == [b, a]


def test_info_plist_option_overrides_default(tmp_path):
    m = make_module(tmp_path)
    assert autolink.info_plist([m], {}) == {"NSDemoUsageDescription": "Uses demo"}
    assert autolink.info_plist([m], {"demo-mod": {"demoText": "Custom & <b>"}})["NSDemoUsageDescription"] == "Custom & <b>"


def test_render_ios(tmp_path):
    m = make_module(tmp_path / "mods")
    gen = tmp_path / "gen"
    autolink.render_ios(gen, [m], {"demo-mod": {"demoText": "A & B"}})
    assert (gen / "runtime/modules/demo-mod/DemoModule.swift").is_file()
    assert "DemoModule.self" in (gen / "runtime/PxModuleRegistry.swift").read_text()
    autolink.render_ios(gen, [], {})  # unlinking removes the old copy
    assert not (gen / "runtime/modules/demo-mod").exists()
    assert "[]" in (gen / "runtime/PxModuleRegistry.swift").read_text()


def test_render_android(tmp_path):
    m = make_module(tmp_path / "mods")
    gen = tmp_path / "gen"
    autolink.render_android(gen, [m])
    g = (gen / "modules/demo-mod/build.gradle.kts").read_text()
    assert 'namespace = "dev.pyxpo.modules.demo"' in g and "androidx.core:core-ktx:1.13.1" in g
    assert (gen / "modules/demo-mod/src/main/AndroidManifest.xml").is_file()
    assert ':px-demo-mod' in (gen / "modules.settings.gradle.kts").read_text()
    assert 'project(":px-demo-mod")' in (gen / "modules.app.gradle.kts").read_text()
    assert "DemoModule()" in (gen / "runtime/java/dev/pyxpo/runtime/PxModuleRegistry.kt").read_text()
    autolink.render_android(gen, [])
    assert not (gen / "modules/demo-mod").exists()
    assert "listOf()" in (gen / "runtime/java/dev/pyxpo/runtime/PxModuleRegistry.kt").read_text()


def test_check_android_wiring(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "settings.gradle.kts").write_text("include(\":app\")\n")
    (tmp_path / "app" / "build.gradle.kts").write_text(autolink.APP_LINE)
    with pytest.raises(BuildError) as e:
        autolink.check_android_wiring(tmp_path)
    assert autolink.SETTINGS_LINE in str(e.value)
    (tmp_path / "settings.gradle.kts").write_text(autolink.SETTINGS_LINE)
    autolink.check_android_wiring(tmp_path)


def test_discover_without_installed_modules(monkeypatch):
    monkeypatch.setattr(autolink, "_entry_points", lambda: [])
    assert autolink.discover() == {}


def test_first_party_modules_found_via_entry_points():
    """The packages in packages/ are installed (tools/dev_install.sh) and found through `pyxpo.modules` entry points."""
    assert sorted(ep.name for ep in autolink._entry_points()) == sorted(autolink.OFFICIAL)
    mods = autolink.discover()
    for name in autolink.OFFICIAL:
        m = mods[name]
        assert m.pkg == autolink.import_name(name) and m.root.name == m.pkg
        assert list((m.root / "ios").glob("*.swift")) and (m.root / "android" / "src" / "main" / "AndroidManifest.xml").is_file()
    assert mods["image-manipulator"].native == "ImageManipulator"


def test_listed_but_not_installed_says_which_package(tmp_path):
    with pytest.raises(BuildError) as e:
        autolink.resolve({"modules": ["image-picker"]}, tmp_path, {})
    assert "pip install pyxpo-image-picker" in str(e.value)
    with pytest.raises(BuildError) as e:
        autolink.resolve({"modules": ["image-pickr"]}, tmp_path, {})
    assert "did you mean 'image-picker'" in str(e.value)


def test_import_of_uninstalled_first_party_module(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "index.py").write_text("from pyxpo_sharing import Share\n")
    with pytest.raises(BuildError) as e:
        autolink.resolve({"modules": []}, tmp_path, {})
    assert "pip install pyxpo-sharing" in str(e.value) and "add 'sharing'" in str(e.value)


def test_python_files_bundles_only_module_python(tmp_path):
    m = make_module(tmp_path, pkg="pyxpo_demo_mod")
    (m.root / "__init__.py").write_text("")
    (m.root / "sub").mkdir()
    (m.root / "sub" / "x.py").write_text("")
    (m.root / "__pycache__").mkdir()
    (m.root / "__pycache__" / "y.py").write_text("")
    arcs = sorted(arc for _, arc in autolink.python_files([m]))
    assert arcs == ["pyxpo_demo_mod/__init__.py", "pyxpo_demo_mod/sub/x.py"]


def test_moved_hint_points_at_package():
    import pyxpo
    with pytest.raises(AttributeError) as e:
        pyxpo.ImagePicker
    msg = str(e.value)
    assert "pip install pyxpo-image-picker" in msg and "from pyxpo_image_picker import ImagePicker" in msg
    assert "'image-picker'" in msg


def test_require_linked(monkeypatch):
    from pyxpo import modules
    from pyxpo.apis import _env
    env = _env.Env({"os": "ios", "modules": []})
    monkeypatch.setattr(_env, "current", env)
    with pytest.raises(modules.ModuleNotLinkedError) as e:
        modules.require_linked("ImageManipulator", "image-manipulator")
    assert "add 'image-manipulator'" in str(e.value).lower() or "Add 'image-manipulator'" in str(e.value)
    with pytest.raises(modules.ModuleNotLinkedError) as e:
        modules.require_linked("ImageManipulator", "image-manipulator", package="pyxpo-image-manipulator")
    assert "pip install pyxpo-image-manipulator" in str(e.value)
    env.update({"modules": ["ImageManipulator"]})
    modules.require_linked("ImageManipulator", "image-manipulator")


def test_check_ios_wiring(tmp_path):
    (tmp_path / "project.yml").write_text("settings:\n  base:\n    GENERATE_INFOPLIST_FILE: NO\n")
    with pytest.raises(BuildError) as e:
        autolink.check_ios_wiring(tmp_path)
    assert "GENERATE_INFOPLIST_FILE: YES" in str(e.value)
    (tmp_path / "project.yml").write_text("settings:\n  base:\n    GENERATE_INFOPLIST_FILE: YES\n")
    autolink.check_ios_wiring(tmp_path)


def test_validate_rejects_injection_and_bad_types():
    ok = {"name": "ok", "native": "X"}
    bad = [
        {"ios": {"classes": ["A"], "infoPlist": {"NSFoo\nOTHER_LDFLAGS = -evil": {"default": "x"}}}},
        {"ios": {"classes": ["A"], "infoPlist": ["NSFoo"]}},
        {"ios": ["A"]},
        {"android": {"namespace": "a.b", "classes": ["A"], "dependencies": "androidx.core:core"}},
        {"android": {"namespace": "a.b", "classes": ["A"], "minSdk": "24"}},
    ]
    for extra in bad:
        with pytest.raises(BuildError):
            autolink.validate(dict(ok, **extra), "f")


def test_discover_skips_duplicate_entry_point(monkeypatch, tmp_path):
    import sys
    import types
    m = make_module(tmp_path / "pkgs", name="third-party", pkg="third_party")
    (m.root / "__init__.py").write_text("")
    mod = types.ModuleType("third_party")
    mod.__file__ = str(m.root / "__init__.py")
    ep = types.SimpleNamespace(name="third-party", load=lambda: mod)
    monkeypatch.setattr(autolink, "_entry_points", lambda: [ep, ep])
    monkeypatch.setitem(sys.modules, "third_party", mod)
    assert list(autolink.discover()) == ["third-party"]
