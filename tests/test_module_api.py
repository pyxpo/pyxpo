import pytest

from pyxpo import module_api as api
from pyxpo.apis import _env


def test_permission_response_shape():
    r = api.permission_response("granted")
    assert r == {"status": "granted", "granted": True, "canAskAgain": True, "expires": "never"}
    assert api.permission_response("denied", False)["granted"] is False
    with pytest.raises(ValueError):
        api.permission_response("maybe")


def test_require_supported(monkeypatch):
    monkeypatch.setattr(_env, "current", _env.Env({"os": "android", "modules": []}))
    assert api.platform() == "android"
    api.require_supported("heic", ios=True, android=True)
    with pytest.raises(api.NotSupportedError):
        api.require_supported("heic encode", android=False)
    monkeypatch.setattr(_env, "current", _env.Env({"os": "ios"}))
    api.require_supported("heic encode", android=False)


def _packages_root():
    """The folder holding the package repos pyxpo-<name> (see tools/dev_install.sh)."""
    import os
    import pathlib
    root = pathlib.Path(os.environ.get("PYXPO_PACKAGES") or pathlib.Path(__file__).resolve().parents[2] / "pyxpo-packages")
    if not root.is_dir():
        pytest.skip("package repos not cloned (tools/dev_install.sh)")
    return root


def test_packages_use_only_public_api():
    import pathlib
    import re
    bad = re.compile(r"from pyxpo(\.apis|\._|\.modules)|import pyxpo\._")
    for f in _packages_root().glob("pyxpo-*/pyxpo_*/**/*.py"):
        assert not bad.search(f.read_text()), f


def test_fake_bridge_roundtrip():
    import asyncio
    from pyxpo.module_testing import FakeBridge

    async def go():
        return await api.call("Demo", "echo", 5, reply=True)

    with FakeBridge().on("Demo", "echo", lambda x: {"v": x}) as fb:
        api.require_linked("Demo", "demo")
        assert asyncio.run(go()) == {"v": 5}
        assert fb.calls == [("Demo", "echo", (5,))]


def test_packages_follow_packaging_hygiene():
    import pathlib
    import re
    for pyproj in _packages_root().glob("pyxpo-*/pyproject.toml"):
        pkg = pyproj.parent
        imp = pkg.name.replace("-", "_")
        text = pyproj.read_text()
        assert (pkg / imp / "py.typed").is_file(), pkg.name
        assert (pkg / "CHANGELOG.md").is_file(), pkg.name
        assert re.search(r'"pyxpo>=\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?,<\d+\.\d+"', text), pkg.name
        assert '"py.typed"' in text, pkg.name


def test_module_constants(monkeypatch):
    from pyxpo.module_testing import FakeBridge
    assert api.constants("Device") == {}
    with FakeBridge("android", constants={"Device": {"brand": "google", "nested": {"a": 1}}}):
        c = api.constants("Device")
        assert c == {"brand": "google", "nested": {"a": 1}}
        c["brand"] = "x"  # a copy: callers cannot change the table
        assert api.constants("Device")["brand"] == "google"
        assert api.constants("Other") == {}
    env = _env.Env({"os": "ios", "module_constants": {"A": {"k": 1}}})
    env.update({"window": {"width": 1.0}})  # later env events carry no constants and must not clear them
    monkeypatch.setattr(_env, "current", env)
    assert api.constants("A") == {"k": 1}
    monkeypatch.setattr(_env, "current", _env.Env({"os": "ios", "module_constants": ["bad"]}))
    assert api.constants("A") == {}
