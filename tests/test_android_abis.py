from __future__ import annotations

import importlib
import zipfile

import pytest

droid = importlib.import_module("pyxpo.build.android")


def _setup(tmp_path, monkeypatch, extra="", fail_abi=None):
    dist = tmp_path / "adist"
    for abi in ("arm64-v8a", "armeabi-v7a"):
        (dist / abi / "prefix" / "lib" / "python3.13").mkdir(parents=True)
        for so in droid.SO_FOR_JNILIBS + ["libpython3.13.so"]:
            (dist / abi / "prefix" / "lib" / so).write_bytes(b"\x7fELF")
    monkeypatch.setattr(droid, "DIST", dist)
    monkeypatch.setattr(droid, "_check_16kb", lambda *a, **k: None)
    monkeypatch.setattr(droid.runtime, "ensure", lambda *a, **k: dist)
    monkeypatch.setenv("ANDROID_HOME", str(tmp_path))

    def install(requires, abi, target, index_args=()):
        target.mkdir(parents=True, exist_ok=True)
        if abi == fail_abi:
            raise droid.BuildError("command failed (1): pip")

    monkeypatch.setattr(droid, "install_requires", install)
    proj = tmp_path / "proj"
    (proj / "app").mkdir(parents=True)
    (proj / "app" / "index.py").write_text("x = 1\n")
    (proj / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "1.0"\n[tool.pyxpo]\nname = "Demo"\n'
                                         'bundle_id = "dev.x.demo"\nrequires = ["numpy"]\n' + extra)
    return proj


def test_armeabi_v7a_is_a_default_abi(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert droid.available_abis() == ["arm64-v8a", "armeabi-v7a"]
    assert droid.ABI_TAGS["armeabi-v7a"] == "android_24_armeabi_v7a"


def test_stage_ships_32bit_arm(tmp_path, monkeypatch):
    proj = _setup(tmp_path, monkeypatch)
    dest = droid.prebuild(proj)
    droid.stage(dest, proj, droid.load_config(proj), False, droid.available_abis())
    gen = dest / "pyxpo-gen"
    assert "abis=arm64-v8a,armeabi-v7a" in (gen / "pyxpo.properties").read_text()
    assert (gen / "jniLibs" / "armeabi-v7a" / "libpython3.13.so").is_file()
    assert (gen / "assets" / "pyxpo" / "stdlib-armeabi-v7a.zip").is_file()
    zipfile.ZipFile(str(gen / "assets" / "pyxpo" / "site-armeabi-v7a.zip")).close()


def test_stage_leaves_out_32bit_arm_without_wheels(tmp_path, monkeypatch, capsys):
    proj = _setup(tmp_path, monkeypatch, fail_abi="armeabi-v7a")
    dest = droid.prebuild(proj)
    assets = dest / "pyxpo-gen" / "assets" / "pyxpo"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "stdlib-armeabi-v7a.zip").write_bytes(b"old")  # from an earlier build that had the wheels
    droid.stage(dest, proj, droid.load_config(proj), False, droid.available_abis())
    gen = dest / "pyxpo-gen"
    assert "abis=arm64-v8a\n" in (gen / "pyxpo.properties").read_text()
    assert not (gen / "jniLibs" / "armeabi-v7a").exists()
    assert sorted(p.name for p in assets.glob("*.zip")) == ["site-arm64-v8a.zip", "stdlib-arm64-v8a.zip"]
    assert "left out armeabi-v7a" in capsys.readouterr().out


def test_stage_fails_when_32bit_arm_is_asked_for(tmp_path, monkeypatch):
    proj = _setup(tmp_path, monkeypatch, extra='abis = ["arm64-v8a", "armeabi-v7a"]\n', fail_abi="armeabi-v7a")
    dest = droid.prebuild(proj)
    with pytest.raises(droid.BuildError):
        droid.stage(dest, proj, droid.load_config(proj), False, droid.available_abis(["arm64-v8a", "armeabi-v7a"]))


def test_64bit_abi_without_wheels_still_fails(tmp_path, monkeypatch):
    proj = _setup(tmp_path, monkeypatch, fail_abi="arm64-v8a")
    dest = droid.prebuild(proj)
    with pytest.raises(droid.BuildError):
        droid.stage(dest, proj, droid.load_config(proj), False, droid.available_abis())


def test_runtime_picks_a_shipped_abi():
    kt = (droid.TEMPLATE / "gen" / "runtime" / "java" / "dev" / "pyxpo" / "runtime" / "PyxpoRuntime.kt").read_text()
    assert 'Build.SUPPORTED_ABIS.first { "stdlib-$it.zip" in shipped }' in kt


def test_moved_project_drops_stale_gradle_state(tmp_path, capsys):
    old = tmp_path / "old" / "android"
    (old / ".gradle").mkdir(parents=True)
    droid._drop_moved_gradle_state(old)
    assert (old / ".gradle" / "pyxpo-root").read_text().strip() == str(old.resolve())
    new = tmp_path / "new" / "android"
    new.parent.mkdir()
    old.rename(new)
    for rel in (".gradle/8.10.2/executionHistory", "app/build/intermediates", "pyxpo-gen/module-api/build"):
        (new / rel).mkdir(parents=True)
    (new / "app" / "src").mkdir()
    droid._drop_moved_gradle_state(new, inside_gradle=True)  # Gradle has the state open: only a hint
    assert "moved from" in capsys.readouterr().out
    assert (new / "app" / "build").is_dir()
    droid._drop_moved_gradle_state(new)
    assert "removing stale Gradle state" in capsys.readouterr().out
    assert not (new / "app" / "build").exists()
    assert not (new / "pyxpo-gen" / "module-api" / "build").exists()
    assert not (new / ".gradle" / "8.10.2").exists()
    assert (new / "app" / "src").is_dir()
    assert (new / ".gradle" / "pyxpo-root").read_text().strip() == str(new.resolve())
    droid._drop_moved_gradle_state(new)  # same place again: nothing to do
    assert "moved from" not in capsys.readouterr().out
