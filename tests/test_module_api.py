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


def test_packages_use_only_public_api():
    import pathlib
    import re
    bad = re.compile(r"from pyxpo(\.apis|\._|\.modules)|import pyxpo\._")
    for f in pathlib.Path(__file__).parents[1].glob("packages/*/pyxpo_*/**/*.py"):
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
    root = pathlib.Path(__file__).resolve().parents[1] / "packages"
    for pyproj in root.glob("*/pyproject.toml"):
        pkg = pyproj.parent
        imp = "pyxpo_" + pkg.name.replace("-", "_")
        text = pyproj.read_text()
        assert (pkg / imp / "py.typed").is_file(), pkg.name
        assert (pkg / "CHANGELOG.md").is_file(), pkg.name
        assert re.search(r'"pyxpo>=\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?,<\d+\.\d+"', text), pkg.name
        assert '"py.typed"' in text, pkg.name
