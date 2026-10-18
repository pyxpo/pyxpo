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
    monkeypatch.setenv("PYXPO_RENDERER", "console")  # not the native Mac app build
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("1\n1\nq\n"))
    import sys
    monkeypatch.setattr(sys, "path", list(sys.path))
    for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        monkeypatch.delitem(sys.modules, m)
    for k in ("PYXPO_TARGET", "PYXPO_APP_NAME", "PYXPO_DEV_URL", "PYXPO_DEV_TOKEN"):  # run sets them; restore after
        monkeypatch.delenv(k, raising=False)
    assert cli.main(["run", "desktop", "--no-reload", "--dir", str(proj)]) == 0


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


def test_prebuild_cli_output(tmp_path, monkeypatch, capsys):
    import importlib

    ios = importlib.import_module("pyxpo.build.ios")
    droid = importlib.import_module("pyxpo.build.android")
    monkeypatch.setattr(ios, "prebuild", lambda p, clean=False: (p / "ios" / "PyxpoApp.xcodeproj").mkdir(parents=True))
    monkeypatch.setattr(droid, "prebuild", lambda p, clean=False: (p / "android").mkdir())
    assert cli.main(["prebuild", "--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "\033[" not in out  # no colour when stdout is not a terminal
    assert "Created Gradle project android/" in out
    assert "Created Xcode project ios/ (PyxpoApp.xcodeproj)" in out
    assert "cd android && ./gradlew assembleRelease" in out and "open ios/PyxpoApp.xcodeproj" in out
    monkeypatch.setattr(ios, "prebuild", lambda p, clean=False: None)
    assert cli.main(["prebuild", "ios", "--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Updated Xcode project ios/" in out and "gradlew" not in out and "ios/ is yours" in out


def test_android_dev_relaunches_until_client_connects(tmp_path, monkeypatch):
    # Android's package-update flow can relaunch the app without our extras; the CLI must relaunch it.
    import argparse
    import json
    import urllib.request

    from pyxpo.dev.server import DevServer

    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "index.py").write_text("x = 1\n")
    (tmp_path / "pyproject.toml").write_text('[tool.pyxpo]\nname = "demo"\nbundle_id = "com.example.demo"\n')
    launches = []

    class FakeDroid:
        @staticmethod
        def adb_path():
            return "adb"

        @staticmethod
        def _run(cmd):
            pass

        @staticmethod
        def launch(app_id, extras):
            launches.append(app_id)
            if len(launches) == 2:  # second launch keeps its extras: the client polls the server
                req = urllib.request.Request(extras["pyxpo_dev_url"] + "/poll?since=0&session=",
                                             headers={"X-Pyxpo-Token": extras["pyxpo_dev_token"]})
                with urllib.request.urlopen(req, timeout=5) as r:
                    json.loads(r.read())

    monkeypatch.setattr(cli, "_dev_port", lambda args, project: 0)
    monkeypatch.setattr(cli, "ANDROID_DEV_CONNECT_TIMEOUT", 0.2)
    monkeypatch.setattr(DevServer, "serve_forever", lambda self: self.stop())
    cli._android_dev(FakeDroid, tmp_path, argparse.Namespace())
    assert launches == ["com.example.demo", "com.example.demo"]


def test_stage_cli(tmp_path, monkeypatch):
    import importlib

    ios = importlib.import_module("pyxpo.build.ios")
    droid = importlib.import_module("pyxpo.build.android")
    seen = []
    monkeypatch.setattr(ios, "stage_project", lambda p, release=False, kind="simulator": seen.append(("ios", release, kind)))
    monkeypatch.setattr(droid, "stage_project", lambda p, release=False: seen.append(("android", release)))
    assert cli.main(["stage", "android", "--release", "--dir", str(tmp_path)]) == 0
    assert cli.main(["stage", "ios", "--kind", "device", "--dir", str(tmp_path)]) == 0
    assert seen == [("android", True), ("ios", False, "device")]


def test_python_dash_m_pyxpo():
    import sys

    r = subprocess.run([sys.executable, "-m", "pyxpo", "stage", "--help"], capture_output=True, text=True)
    assert r.returncode == 0 and "--kind" in r.stdout


def test_add_lib_missing_32bit_wheel_is_only_a_note(tmp_path, monkeypatch, capsys):
    cli.main(["create", "demo", "--dir", str(tmp_path)])
    proj = tmp_path / "demo"

    def fake_run(cmd, **kw):
        ok = cmd[cmd.index("--platform") + 1] != "android_24_armeabi_v7a"
        return subprocess.CompletedProcess(cmd, 0 if ok else 1, "", "" if ok else "ERROR: no matching distribution")

    monkeypatch.setattr(libs.subprocess, "run", fake_run)
    assert cli.main(["add-lib", "numpy", "--dir", str(proj)]) == 0
    out = capsys.readouterr().out
    assert "android_24_armeabi_v7a" in out and "optional" in out and "32-bit" in out
