from __future__ import annotations

import subprocess

from pyxpo import cli, libs
from pyxpo.config import load_config


def test_create_and_config(tmp_path):
    assert cli.main(["create", "demo", "--dir", str(tmp_path)]) == 0
    proj = tmp_path / "demo"
    assert (proj / "app" / "_layout.py").is_file() and (proj / "app" / "index.py").is_file() and (proj / "app" / "details" / "[id].py").is_file() and (proj / ".gitignore").is_file()
    cfg = load_config(proj)
    assert cfg["name"] == "demo" and cfg["bundle_id"] == "com.example.demo" and cfg["requires"] == []
    assert cli.main(["create", "demo", "--dir", str(tmp_path)]) == 2
    assert cli.main(["create", "bad name", "--dir", str(tmp_path)]) == 2


def test_run_desktop_smoke(tmp_path, monkeypatch):
    cli.main(["create", "demo", "--dir", str(tmp_path)])
    proj = tmp_path / "demo"
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("1\n1\nq\n"))
    import sys
    monkeypatch.setattr(sys, "path", list(sys.path))
    for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        monkeypatch.delitem(sys.modules, m)
    assert cli.main(["run", "desktop", "--dir", str(proj)]) == 0


def test_add_lib(tmp_path, monkeypatch):
    cli.main(["create", "demo", "--dir", str(tmp_path)])
    proj = tmp_path / "demo"

    def fake_run(cmd, **kw):
        tag = cmd[cmd.index("--platform") + 1]
        ok = "android" in tag
        return subprocess.CompletedProcess(cmd, 0 if ok else 1, "", "" if ok else "ERROR: no matching distribution")

    monkeypatch.setattr(libs.subprocess, "run", fake_run)
    assert cli.main(["add-lib", "numpy", "--dir", str(proj)]) == 1  # ios missing
    assert load_config(proj)["requires"] == ["numpy"]
    assert cli.main(["add-lib", "tensorflow", "--dir", str(proj)]) == 1
    assert load_config(proj)["requires"] == ["numpy"]


def test_prebuild_cli(tmp_path, monkeypatch):
    import importlib

    ios = importlib.import_module("pyxpo.build.ios")
    droid = importlib.import_module("pyxpo.build.android")
    seen = []
    monkeypatch.setattr(ios, "prebuild", lambda p, clean=False: seen.append(("ios", clean)) or p / "ios")
    monkeypatch.setattr(droid, "prebuild", lambda p, clean=False: seen.append(("android", clean)) or p / "android")
    assert cli.main(["prebuild", "ios", "--dir", str(tmp_path)]) == 0
    assert cli.main(["prebuild", "--clean", "--yes", "--dir", str(tmp_path)]) == 0
    assert seen == [("ios", False), ("android", True), ("ios", True)]
    assert cli.main(["prebuild", "ios", "--clean", "--dir", str(tmp_path)]) == 2  # needs --yes when not a tty
