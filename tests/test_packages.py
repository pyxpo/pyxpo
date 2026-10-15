"""The native module packages in packages/ build into wheels and sdists that autolinking can use."""
import importlib.util
import json
import re
from pathlib import Path

import pytest

from pyxpo.build import autolink

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_packages", ROOT / "tools" / "build_packages.py")
bp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bp)


def _can_build_offline():
    try:
        import build  # noqa: F401
        import setuptools
    except ImportError:
        return False
    return int(setuptools.__version__.split(".")[0]) >= 77


def test_every_official_module_has_a_package():
    assert bp.packages() == sorted(autolink.OFFICIAL)
    for name in bp.packages():
        d = ROOT / "packages" / name
        meta = json.loads((d / bp.import_name(name) / "pyxpo-module.json").read_text())
        assert meta["name"] == name
        toml = (d / "pyproject.toml").read_text()
        assert 'name = "%s"' % autolink.dist_name(name) in toml
        assert re.search(r'\[project\.entry-points\."pyxpo\.modules"\]\n%s = "%s"' % (name, bp.import_name(name)), toml)
        assert re.search(r'dependencies = \["pyxpo>=', toml)


def test_core_no_longer_ships_modules():
    assert not (ROOT / "src" / "pyxpo" / "modules").is_dir()
    assert "modules/**" not in (ROOT / "pyproject.toml").read_text()


@pytest.mark.skipif(not _can_build_offline(), reason="needs `build` and setuptools>=77 (tools/dev_install.sh)")
@pytest.mark.parametrize("name", sorted(autolink.OFFICIAL))
def test_package_wheel_and_sdist_carry_native_files(name, tmp_path):
    assert bp.build(name, tmp_path, isolation=False) == []
    whl = next(tmp_path.glob("*.whl"))
    assert whl.name.startswith(autolink.import_name(name) + "-")
    assert bp.expected_files(name)  # sanity: the checker really compared something
    assert any(f.endswith(".swift") for f in bp.expected_files(name))
    assert any(f.endswith(".kt") for f in bp.expected_files(name))
