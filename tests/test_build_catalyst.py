"""Native Mac desktop app (the iOS shell built for Mac Catalyst): slice lookup, build settings, CLI choice, launcher."""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

from pyxpo import cli, native_config
from pyxpo.build import ios
from pyxpo.config import load_config


def fake_xcframework(root: Path, *slices: str) -> Path:
    xc = root / "Python.xcframework"
    for s in slices:
        (xc / s / "Python.framework" / "Headers").mkdir(parents=True)
    return root


def test_slice_kind():
    assert ios._slice_kind("ios-arm64-maccatalyst") == "catalyst"
    assert ios._slice_kind("ios-arm64_x86_64-simulator") == "simulator"
    assert ios._slice_kind("ios-arm64") == "device"


def test_find_slice(tmp_path, monkeypatch):
    monkeypatch.setattr(ios, "DIST", tmp_path)
    assert ios.find_slice("catalyst") is None
    fake_xcframework(tmp_path, "ios-arm64", "ios-arm64_x86_64-simulator")
    assert ios.find_slice("catalyst") is None
    assert ios.find_slice("device").name == "ios-arm64"
    fake_xcframework(tmp_path, "ios-arm64-maccatalyst")
    assert ios.find_slice("catalyst").name == "ios-arm64-maccatalyst"
    assert ios.find_slice("simulator").name == "ios-arm64_x86_64-simulator"


def _nc(tmp_path):
    p = tmp_path / "proj"
    p.mkdir()
    (p / "pyproject.toml").write_text('[project]\nname="x"\nversion="1.0.0"\n[tool.pyxpo]\nname = "Demo"\nbundle_id = "com.acme.demo"\n')
    return native_config.resolve(load_config(p), p)


def test_xcconfig_catalyst_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(ios, "DIST", tmp_path / "dist")
    fake_xcframework(tmp_path / "dist", "ios-arm64", "ios-arm64_x86_64-simulator")
    nc = _nc(tmp_path)
    text = ios.xcconfig_text(nc)
    assert "SUPPORTS_MACCATALYST" not in text and "sdk=macosx*" not in text
    fake_xcframework(tmp_path / "dist", "ios-arm64-maccatalyst")
    text = ios.xcconfig_text(nc)
    assert "SUPPORTS_MACCATALYST = YES" in text
    assert "SUPPORTS_MAC_DESIGNED_FOR_IPHONE_IPAD = NO" in text
    assert "DERIVE_MACCATALYST_PRODUCT_BUNDLE_IDENTIFIER = NO" in text
    assert "HEADER_SEARCH_PATHS[sdk=macosx*]" in text and "ios-arm64-maccatalyst/Python.framework/Headers" in text


def test_catalyst_pip_tag():
    assert ios.PIP_TAGS["catalyst"].startswith("macosx_") and ios.PIP_TAGS["catalyst"].endswith("_arm64")


@pytest.mark.parametrize("platform,renderer,has_slice,expected", [
    ("darwin", None, True, True),
    ("darwin", None, False, False),
    ("darwin", "console", True, False),
    ("linux", None, True, False),
])
def test_native_desktop_available(monkeypatch, platform, renderer, has_slice, expected):
    monkeypatch.setattr(sys, "platform", platform)
    if renderer:
        monkeypatch.setenv("PYXPO_RENDERER", renderer)
    else:
        monkeypatch.delenv("PYXPO_RENDERER", raising=False)
    monkeypatch.setattr(ios, "find_slice", lambda kind: Path("/x") if has_slice and kind == "catalyst" else None)
    assert cli._native_desktop_available() is expected


def test_run_and_build_desktop_pick_catalyst(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_ios", lambda args, run, kind="simulator": calls.append((run, kind)) or 0)
    monkeypatch.setattr(cli, "_native_desktop_available", lambda: True)
    assert cli.main(["run", "desktop"]) == 0
    assert cli.main(["build", "desktop"]) == 0
    assert calls == [(True, "catalyst"), (False, "catalyst")]


def test_run_desktop_preview_skips_native(tmp_path, monkeypatch):
    cli.main(["create", "demo", "--dir", str(tmp_path)])
    monkeypatch.setattr(cli, "_native_desktop_available", lambda: True)
    monkeypatch.setattr(cli, "_ios", lambda *a, **k: pytest.fail("native build on --preview"))
    monkeypatch.setenv("PYXPO_RENDERER", "console")
    monkeypatch.setattr("sys.stdin", io.StringIO("q\n"))
    monkeypatch.setattr(sys, "path", list(sys.path))
    for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        monkeypatch.delitem(sys.modules, m)
    for k in ("PYXPO_TARGET", "PYXPO_APP_NAME", "PYXPO_DEV_URL", "PYXPO_DEV_TOKEN"):  # run sets them; restore after
        monkeypatch.delenv(k, raising=False)
    assert cli.main(["run", "desktop", "--preview", "--no-reload", "--dir", str(tmp_path / "demo")]) == 0


class FakePopen:
    def __init__(self, args):
        self.args, self.code, self.terminated = args, None, False

    def poll(self):
        return self.code

    def wait(self):
        self.code = 0 if self.code is None else self.code
        return self.code

    def terminate(self):
        self.terminated = True
        self.code = -15


def test_mac_app_launch_args(tmp_path, monkeypatch):
    app = tmp_path / "Demo.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    procs, runs = [], []
    monkeypatch.setattr(ios.subprocess, "Popen", lambda a: procs.append(FakePopen(a)) or procs[-1])
    monkeypatch.setattr(ios.subprocess, "run", lambda a, check=False: runs.append(a))
    monkeypatch.setenv("PYXPO_SNAPSHOT_DIR", "/snap")
    monkeypatch.setenv("UNRELATED", "no")
    m = ios.run_mac(app, {"PYXPO_DEV_URL": "http://127.0.0.1:1"})
    a = procs[0].args
    assert a[:3] == ["open", "-n", "-W"] and a[-1] == str(app)
    envs = [a[i + 1] for i, x in enumerate(a) if x == "--env"]
    assert "PYXPO_STDIO=1" in envs and "PYXPO_DEV_URL=http://127.0.0.1:1" in envs and "PYXPO_SNAPSHOT_DIR=/snap" in envs
    assert not any(e.startswith("UNRELATED") for e in envs)
    log = Path(a[a.index("--stdout") + 1])
    assert log.is_file() and not str(log).startswith(str(tmp_path))  # never next to the app: external volumes break launch
    m.terminate()
    assert procs[0].terminated and runs == [["pkill", "-f", str(app / "Contents" / "MacOS" / "Demo")]]
    assert m.wait() == -15
