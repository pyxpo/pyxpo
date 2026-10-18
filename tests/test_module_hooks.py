"""Module build hooks: `"build": {"hook": ...}` in pyxpo-module.json, build modes and shipped module data."""
import json
import sys
import types
from pathlib import Path

import pytest

from pyxpo import module_hooks, modules
from pyxpo.app_config import resolve
from pyxpo.app_config.schema import ConfigError
from pyxpo.build import android, app_json, autolink
from pyxpo.build.runtime import BuildError
from pyxpo.config import load_config


def fake_module(tmp_path, monkeypatch, hook_src, name="hooked", pkg="pyxpo_hooked_test", spec=None):
    """Installs a package `pkg` with a pyxpo-module.json whose build hook is `configure` in `pkg.build`."""
    root = tmp_path / "site" / pkg
    root.mkdir(parents=True)
    (root / "__init__.py").write_text("")
    (root / "build.py").write_text(hook_src)
    (root / "pyxpo-module.json").write_text(json.dumps({
        "schemaVersion": 1, "name": name, "native": "Hooked",
        "build": {"hook": spec or pkg + ".build:configure"}}))
    monkeypatch.syspath_prepend(str(tmp_path / "site"))
    for k in [k for k in sys.modules if k == pkg or k.startswith(pkg + ".")]:
        del sys.modules[k]
    import importlib
    mod = importlib.import_module(pkg)
    ep = types.SimpleNamespace(name=name, load=lambda: mod)
    monkeypatch.setattr(autolink, "_entry_points", lambda: [ep])
    module_hooks._warned.clear()
    return mod


def project(tmp_path, extra="", modules_list='["hooked"]'):
    p = tmp_path / "proj"
    (p / "app").mkdir(parents=True)
    (p / "app" / "index.py").write_text("default = None\n")
    (p / "pyproject.toml").write_text('[tool.pyxpo]\nname = "Demo"\nmodules = %s\n%s' % (modules_list, extra))
    return p


HOOK = """
def configure(ctx):
    ctx.config.setdefault("extra", {})["from_hook"] = ctx.mode
    ctx.ship({"mode": ctx.mode, "opt": ctx.options.get("level")})
"""


def test_hook_edits_config_and_ships_data(tmp_path, monkeypatch):
    fake_module(tmp_path, monkeypatch, HOOK)
    p = project(tmp_path, "[tool.pyxpo.module_options.hooked]\nlevel = 3\n")
    cfg = load_config(p, "staging")
    assert cfg["extra"]["from_hook"] == "staging"
    nc = resolve(cfg, p)
    assert app_json.public(nc)["modules"] == {"hooked": {"mode": "staging", "opt": 3}}
    assert app_json.public(nc)["extra"]["from_hook"] == "staging"


def test_no_hooks_no_modules_key(tmp_path, monkeypatch):
    monkeypatch.setattr(autolink, "_entry_points", lambda: [])
    p = project(tmp_path, modules_list="[]")
    assert "modules" not in app_json.public(resolve(load_config(p), p))


def test_build_mode(monkeypatch):
    monkeypatch.delenv(module_hooks.MODE_ENV, raising=False)
    assert module_hooks.build_mode() == "development"
    assert module_hooks.build_mode(True) == "production"
    monkeypatch.setenv(module_hooks.MODE_ENV, "staging")
    assert module_hooks.build_mode(True) == "staging"
    for bad in ("Staging", "../x", "a b", "", "x" * 40, "-x"):
        monkeypatch.setenv(module_hooks.MODE_ENV, bad)
        if bad:
            with pytest.raises(ConfigError, match="build mode"):
                module_hooks.build_mode()
    with pytest.raises(ConfigError):
        module_hooks.check_mode("prod/../../etc")


def test_load_config_uses_env_mode(tmp_path, monkeypatch):
    fake_module(tmp_path, monkeypatch, HOOK)
    monkeypatch.setenv(module_hooks.MODE_ENV, "preview")
    assert load_config(project(tmp_path))["extra"]["from_hook"] == "preview"


def test_hook_must_live_in_its_package(tmp_path, monkeypatch):
    fake_module(tmp_path, monkeypatch, HOOK, spec="os.path:join")
    with pytest.raises(ConfigError, match="its own package"):
        load_config(project(tmp_path))


def test_hook_not_callable(tmp_path, monkeypatch):
    fake_module(tmp_path, monkeypatch, "configure = 5\n")
    with pytest.raises(ConfigError, match="not a function"):
        load_config(project(tmp_path))


def test_bad_hook_spec_fails_validation():
    with pytest.raises(BuildError, match="build.hook"):
        autolink.validate({"name": "ok", "native": "X", "build": {"hook": "no colon"}}, "f")
    with pytest.raises(BuildError):
        autolink.validate({"name": "ok", "native": "X", "build": "pkg:fn"}, "f")
    autolink.validate({"name": "ok", "native": "X", "build": {"hook": "pkg.sub:fn"}}, "f")


def test_hook_errors(tmp_path, monkeypatch):
    fake_module(tmp_path, monkeypatch, "def configure(ctx):\n    raise RuntimeError('boom')\n")
    with pytest.raises(ConfigError, match="build hook .* failed: RuntimeError: boom"):
        load_config(project(tmp_path))
    fake_module(tmp_path / "b", monkeypatch, "def configure(ctx):\n    ctx.fail('no key')\n")
    with pytest.raises(ConfigError, match="hooked: no key"):
        load_config(project(tmp_path / "b"))
    fake_module(tmp_path / "c", monkeypatch, "def configure(ctx):\n    return 5\n")
    with pytest.raises(ConfigError, match="return None or the config"):
        load_config(project(tmp_path / "c"))
    fake_module(tmp_path / "d", monkeypatch, "def configure(ctx):\n    ctx.ship({1, 2})\n")
    with pytest.raises(ConfigError, match="JSON"):
        load_config(project(tmp_path / "d"))


def test_hook_skipped_when_not_listed(tmp_path, monkeypatch):
    fake_module(tmp_path, monkeypatch, "def configure(ctx):\n    raise RuntimeError('ran')\n")
    p = project(tmp_path, modules_list="[]")
    assert "_module_data" not in load_config(p)


def test_warn_once(tmp_path, monkeypatch, capsys):
    fake_module(tmp_path, monkeypatch, "def configure(ctx):\n    ctx.warn('careful')\n")
    p = project(tmp_path)
    load_config(p)
    load_config(p)
    out = capsys.readouterr()
    assert (out.out + out.err).count("hooked: careful") == 1


def test_build_data_from_env(monkeypatch):
    monkeypatch.setenv(module_hooks.DATA_ENV, json.dumps({"env": {"vars": {"A": 1}}}))
    from pyxpo.apis import constants
    monkeypatch.setattr(constants, "_load", lambda: {})
    data = modules.build_data("env")
    assert data == {"vars": {"A": 1}}
    data["vars"]["A"] = 2
    assert modules.build_data("env") == {"vars": {"A": 1}}
    assert modules.build_data("other") is None
    monkeypatch.setattr(constants, "_load", lambda: {"modules": {"env": {"mode": "production"}}})
    assert modules.build_data("env") == {"mode": "production"}


def test_android_zip_skips_dotfiles():
    assert android.ships_in_app(Path("app/index.py"))
    assert android.ships_in_app(Path("assets/img/logo.png"))
    for rel in ("app/.env", "app/.env.local", "assets/.DS_Store", "app/.git/config", "app/__pycache__/x.pyc"):
        assert not android.ships_in_app(Path(rel)), rel


def test_cli_mode_flag(monkeypatch):
    from pyxpo import cli
    monkeypatch.delenv(module_hooks.MODE_ENV, raising=False)
    assert cli.main(["build", "web", "--mode", "Bad/Mode"]) == 2
