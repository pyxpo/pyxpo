"""Native Windows desktop app: the module-call channel, platform answers, the build (staging next to a prebuilt
shell) and the CLI choice. Runs on any OS: the shell is a fake folder and the bridge a recorder."""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

from pyxpo import cli, module_api, modules
from pyxpo.apis import _env
from pyxpo.apis.platform import Platform
from pyxpo.build import windows
from pyxpo.build.android import BuildError
from pyxpo.channel_native import WINDOWS_SHELL_CALLS, WindowsChannel


class Bridge:
    def __init__(self):
        self.posted = []
        self.handler = None

    def post(self, payload):
        self.posted.append(json.loads(payload))

    def set_event_handler(self, fn):
        self.handler = fn


def _channel(backend):
    bridge = Bridge()
    ch = WindowsChannel(bridge=bridge, backend=backend)
    events = []
    done = threading.Event()

    def on_event(s):
        events.append(json.loads(s))
        done.set()

    ch.set_event_handler(on_event)
    return ch, bridge, events, done


def test_channel_passes_batches_without_calls():
    ch, bridge, _, _ = _channel(lambda *a: pytest.fail("backend called"))
    ch.post('[{"op":"create","id":2,"type":"View","props":{}}]')
    assert bridge.posted == [[{"op": "create", "id": 2, "type": "View", "props": {}}]]
    assert bridge.handler is not None


def test_channel_routes_module_calls_to_backend():
    seen = []
    ch, bridge, events, done = _channel(lambda m, meth, args: seen.append((m, meth, args)) or {"ok": 1})
    ops = [{"op": "create", "id": 2, "type": "View", "props": {}},
           {"op": "call", "id": 7, "module": "ImagePicker", "method": "pick", "args": [True], "reply": True},
           {"op": "call", "id": 8, "module": "Clipboard", "method": "set_string", "args": ["x"], "reply": True}]
    ch.post(json.dumps(ops, separators=(",", ":")))
    assert done.wait(5)
    # The shell gets the tree ops and its own calls; the picker runs in Python.
    assert bridge.posted == [[ops[0], ops[2]]]
    assert seen == [("ImagePicker", "pick", [True])]
    assert events == [{"event": "call_result", "id": 7, "payload": {"value": {"ok": 1}}}]


def test_channel_backend_error_becomes_call_error():
    def boom(*a):
        raise RuntimeError("no picker")

    ch, bridge, events, done = _channel(boom)
    ch.post(json.dumps([{"op": "call", "id": 3, "module": "ImagePicker", "method": "pick", "args": [],
                         "reply": True}], separators=(",", ":")))
    assert done.wait(5)
    assert bridge.posted == []
    assert events == [{"event": "call_result", "id": 3, "payload": {"error": "no picker"}}]


def test_channel_no_reply_sends_no_event():
    ran = threading.Event()
    ch, _, events, _ = _channel(lambda *a: ran.set())
    ch.post(json.dumps([{"op": "call", "id": 4, "module": "Haptics", "method": "impact", "args": []}],
                       separators=(",", ":")))
    assert ran.wait(5)
    ch._pool.shutdown(wait=True)
    assert events == []


def test_shell_calls_cover_builtin_modules():
    assert {"Scroll", "Alert", "Clipboard", "Linking", "Back", "Keyboard"} <= WINDOWS_SHELL_CALLS


@pytest.fixture
def windows_env():
    env = _env.current
    old = env._data.get("os")
    env._data["os"] = "windows"
    yield env
    env._data["os"] = old


def test_platform_answers_on_windows(windows_env):
    assert module_api.platform() == "desktop"
    assert Platform.select({"desktop": "d", "default": "x"}) == "d"
    assert Platform.select({"windows": "w", "desktop": "d"}) == "w"
    assert Platform.select({"native": "n", "default": "x"}) == "n"
    modules.require_linked("ImagePicker", "image-picker")  # module calls run in Python: never "not linked"


# --- build ---------------------------------------------------------------------------------------------------

def fake_shell(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / windows.SHELL_EXE).write_bytes(b"MZ")
    (root / "pyxpo_native.dll").write_bytes(b"MZ")
    (root / "PyxpoShell.pdb").write_bytes(b"x")
    (root / "PyxpoShell.pri").write_bytes(b"pri")
    (root / "pyxpo-app.json").write_text("{}")
    (root / "python").mkdir()
    (root / "python" / "python313.zip").write_bytes(b"PK")
    return root


def _project(tmp_path, tool=""):
    p = tmp_path / "proj"
    (p / "app").mkdir(parents=True)
    (p / "app" / "main.py").write_text("print('hi')\n")
    (p / "pyproject.toml").write_text('[project]\nname="x"\nversion="1.0.0"\n[tool.pyxpo]\nname = "Demo App"\n'
                                      'bundle_id = "com.acme.demo"\n' + tool)
    return p


def test_shell_available(tmp_path):
    assert not windows.shell_available(tmp_path / "none")
    shell = fake_shell(tmp_path / "shell")
    assert windows.shell_available(shell)
    (shell / "pyxpo_native.dll").unlink()
    assert not windows.shell_available(shell)


def test_exe_name():
    assert windows.exe_name({"product_name": "Demo App"}) == "Demo App"
    assert windows.exe_name({"product_name": 'a<b>:c"d/e\\f|g?h*i.'}) == "abcdefghi"
    assert windows.exe_name({"product_name": " .. "}) == "PyxpoApp"


def test_window_config():
    nc = {"name": "Demo"}
    assert windows.window_config({}, nc) == {"title": "Demo", "width": 1024, "height": 768, "module": windows.ENTRY}
    out = windows.window_config({"windows": {"title": "T", "size": [800, 600]}},
                                {"name": "Demo", "background_color": "#112233", "user_interface_style": "dark"})
    assert out == {"title": "T", "width": 800, "height": 600, "module": windows.ENTRY,
                   "background_color": "#112233", "user_interface_style": "dark"}
    assert "user_interface_style" not in windows.window_config({}, {"name": "D", "user_interface_style": "automatic"})
    for bad in ([800], [0, 600], ["800", 600], "800x600"):
        with pytest.raises(BuildError):
            windows.window_config({"windows": {"size": bad}}, nc)


def test_stage(tmp_path, monkeypatch):
    shell = fake_shell(tmp_path / "shell")
    project = _project(tmp_path, '[tool.pyxpo.windows]\nsize = [900, 700]\n')
    reqs = []
    monkeypatch.setattr(windows, "install_requires", lambda r, target, idx: reqs.append((r, target)))
    exe = windows.stage(project, shell=shell)
    out = project / "build" / "windows" / "DemoApp"  # product_name drops spaces
    assert exe == out / "DemoApp.exe" and exe.read_bytes() == b"MZ"
    assert not (out / windows.SHELL_EXE).exists()
    assert not (out / "PyxpoShell.pdb").exists()
    assert (out / "DemoApp.pri").read_bytes() == b"pri" and not (out / "PyxpoShell.pri").exists()
    assert (out / "pyxpo_native.dll").is_file() and (out / "python" / "python313.zip").is_file()
    assert (out / "app" / "app" / "main.py").is_file()
    assert (out / "app" / "pyxpo" / "__init__.py").is_file()
    assert json.loads((out / "app" / "pyxpo" / "desktop_modules.json").read_text()) == {}
    cfg = json.loads((out / "pyxpo-app.json").read_text())
    assert cfg["title"] == "Demo App" and (cfg["width"], cfg["height"]) == (900, 700)
    assert cfg["module"] == windows.ENTRY
    assert reqs and reqs[0][1] == out / "app_packages"
    # A second build replaces the first.
    (out / "stale.txt").write_text("x")
    windows.stage(project, shell=shell)
    assert not (out / "stale.txt").exists()


def test_stage_without_shell(tmp_path):
    project = _project(tmp_path)
    with pytest.raises(BuildError, match="no Windows shell"):
        windows.stage(project, shell=tmp_path / "missing")


def test_build_needs_windows_or_dist(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.delenv("PYXPO_WINDOWS_DIST", raising=False)
    with pytest.raises(BuildError, match="builds on Windows"):
        windows.build(tmp_path)
    shell = fake_shell(tmp_path / "shell")
    monkeypatch.setenv("PYXPO_WINDOWS_DIST", str(shell))
    monkeypatch.setattr(windows, "install_requires", lambda *a: None)
    exe = windows.build(_project(tmp_path))
    assert exe.name == "DemoApp.exe"


def test_install_requires_pip_args(tmp_path, monkeypatch):
    runs = []
    monkeypatch.setattr(windows, "_run", lambda cmd: runs.append(cmd))
    target = tmp_path / "pkgs"
    windows.install_requires([], target)
    assert target.is_dir() and runs == []
    windows.install_requires(["pillow"], target, ["--index-url", "https://x"])
    cmd = [str(c) for c in runs[0]]
    assert cmd[cmd.index("--platform") + 1] == "win_amd64"
    assert cmd[cmd.index("--python-version") + 1] == "3.13"
    assert "--only-binary=:all:" in cmd and cmd[-3:] == ["--index-url", "https://x", "pillow"]


# --- CLI -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("platform,renderer,has_shell,expected", [
    ("win32", None, True, True),
    ("win32", None, False, False),
    ("win32", "console", True, False),
    ("darwin", None, True, False),
])
def test_native_windows_available(monkeypatch, platform, renderer, has_shell, expected):
    monkeypatch.setattr(sys, "platform", platform)
    if renderer:
        monkeypatch.setenv("PYXPO_RENDERER", renderer)
    else:
        monkeypatch.delenv("PYXPO_RENDERER", raising=False)
    monkeypatch.setattr(windows, "shell_available", lambda path=None: has_shell)
    assert cli._native_windows_available() is expected


def test_run_and_build_desktop_pick_windows(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(cli, "_windows", lambda args, run: calls.append(run) or 0)
    monkeypatch.setattr(cli, "_native_windows_available", lambda: True)
    monkeypatch.setattr(cli, "_ios", lambda *a, **k: pytest.fail("catalyst build on Windows"))
    assert cli.main(["run", "desktop"]) == 0
    assert cli.main(["build", "desktop"]) == 0
    assert calls == [True, False]


def test_cli_build_error_is_printed(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("PYXPO_WINDOWS_DIST", str(tmp_path / "missing"))
    _project(tmp_path)
    assert cli.main(["build", "desktop", "--dir", str(tmp_path / "proj")]) == 1
    assert "no Windows shell" in capsys.readouterr().err


# --- desktop backends on Windows -------------------------------------------------------------------------------

def test_sharing_uses_explorer_and_clip(monkeypatch):
    from pyxpo_sharing import desktop

    runs = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(desktop.subprocess, "run", lambda cmd, **kw: runs.append((cmd, kw.get("input"))))
    desktop.call("share", [["file:///C:/pics/a.png", "C:/pics/b.png"], "", "", ""])
    desktop.call("share", [[], "héllo", "", ""])
    assert runs[0] == (["explorer", "/select,", "C:\\pics\\a.png"], None)
    assert runs[1] == (["clip"], b"\xff\xfe" + "héllo".encode("utf-16-le"))


def test_image_picker_uses_file_dialog(tmp_path, monkeypatch):
    from pyxpo_image_picker import desktop

    imgs = []
    for n in ("a.png", "b.png", "c.png"):
        f = tmp_path / n
        f.write_bytes(b"\x89PNG")
        imgs.append(str(f))
    seen = []

    class R:
        returncode = 0
        stdout = "\n".join(imgs) + "\n"

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(desktop, "_asset", lambda p: {"uri": p})
    monkeypatch.setattr(desktop.subprocess, "run", lambda cmd, **kw: seen.append(cmd) or R())
    out = desktop.pick(True, 2, "images")
    assert [a["uri"] for a in out["assets"]] == imgs[:2]
    assert seen[0][:4] == ["powershell", "-NoProfile", "-STA", "-Command"]
    assert "Multiselect = $true" in seen[0][4] or "true" in seen[0][4]
