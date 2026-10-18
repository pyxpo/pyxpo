"""Windows build: the native desktop app. A prebuilt WinUI 3 shell (`PyxpoShell.exe`) embeds CPython through
`pyxpo_native.dll` (bridge + layout engine) and draws the same ops as the iOS and Android shells, with native
XAML controls. A build copies that shell, renames it after the app and stages Python code next to it:

    build/windows/<Name>/
        <Name>.exe, *.dll        the shell (.NET 8 + Windows App SDK, self-contained)
        pyxpo_native.dll         bridge + layout engine
        python/                  CPython 3.13 embeddable distribution
        app/                     the project's app/ and assets/, the pyxpo package, linked modules
        app_packages/            [tool.pyxpo] requires, as win_amd64 wheels
        pyxpo-app.json           window title and size, entry module
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Dict, List, Optional

from .. import native_config
from ..config import load_config, pip_index_args
from ..module_hooks import build_mode
from . import app_json, autolink, runtime
from .android import BuildError, _run
from .ios import _stage_app

SHELL_EXE = "PyxpoShell.exe"
PIP_TAG = "win_amd64"
ENTRY = "pyxpo.router.entry"
DEFAULT_SIZE = (1024, 768)
# The shell's files that a build leaves behind: debug symbols and the shell's own sample config.
SKIP = (".pdb", "pyxpo-app.json")


def dist() -> Path:
    return runtime.dist_path("windows")


def shell_available(path: Optional[Path] = None) -> bool:
    d = Path(path) if path is not None else dist()
    return (d / SHELL_EXE).is_file() and (d / "pyxpo_native.dll").is_file() and (d / "python").is_dir()


def exe_name(nc: Dict[str, object]) -> str:
    """A file name Windows accepts, from the product name."""
    name = "".join(c for c in str(nc["product_name"]) if c not in '<>:"/\\|?*' and ord(c) >= 32).strip(" .")
    return name or "PyxpoApp"


def window_config(cfg: Dict[str, object], nc: Dict[str, object]) -> Dict[str, object]:
    win = cfg.get("windows") if isinstance(cfg.get("windows"), dict) else {}
    size = win.get("size") or list(DEFAULT_SIZE)
    if not (isinstance(size, list) and len(size) == 2 and all(isinstance(v, int) and v > 0 for v in size)):
        raise BuildError("[tool.pyxpo.windows] size must be [width, height] in pixels, got %r" % (size,))
    out = {"title": str(win.get("title") or nc["name"]), "width": size[0], "height": size[1], "module": ENTRY}
    # Same keys as the iOS shell's app config: the window colour under the root view, and light / dark lock.
    if nc.get("background_color"):
        out["background_color"] = str(nc["background_color"])
    style = str(nc.get("user_interface_style") or "automatic")
    if style in ("light", "dark"):
        out["user_interface_style"] = style
    return out


def stage(project: Path, release: bool = False, shell: Optional[Path] = None) -> Path:
    """Builds `build/windows/<Name>/` and returns the path of `<Name>.exe`."""
    project = Path(project).resolve()
    cfg = load_config(project, build_mode(release))
    nc = native_config.resolve(cfg, project)
    shell = Path(shell) if shell is not None else runtime.ensure("windows", path=dist())
    if not shell_available(shell):
        raise BuildError("no Windows shell in %s (needs %s, pyxpo_native.dll and python/); build it with "
                         "tools/build_windows_shell.ps1 or set PYXPO_WINDOWS_DIST" % (shell, SHELL_EXE))
    name = exe_name(nc)
    out = project / "build" / "windows" / name
    if out.exists():
        shutil.rmtree(str(out))
    shutil.copytree(str(shell), str(out), ignore=lambda d, names: [n for n in names if n.endswith(SKIP)])
    (out / SHELL_EXE).rename(out / (name + ".exe"))
    # An unpackaged WinUI app loads its XAML resources from `<exe name>.pri`: rename it with the exe.
    pri = out / (Path(SHELL_EXE).stem + ".pri")
    if pri.is_file():
        pri.rename(out / (name + ".pri"))

    linked = autolink.link(cfg, project)
    root = out / "app"
    _stage_app(project, root, release, linked.modules)
    app_json.write(root / "pyxpo", nc)
    # Module calls run in Python on Windows (each package's desktop.py); the app has no metadata to discover them.
    (root / "pyxpo" / "desktop_modules.json").write_text(
        json.dumps({m.native: m.pkg for m in linked.modules}, indent=2, sort_keys=True))
    install_requires(list(cfg.get("requires", [])), out / "app_packages", pip_index_args(cfg, project))
    (out / "pyxpo-app.json").write_text(json.dumps(window_config(cfg, nc), indent=2, sort_keys=True))
    exe = out / (name + ".exe")
    print("built %s" % exe)
    return exe


def install_requires(requires: List[str], target: Path, index_args: List[str] = ()) -> None:
    if target.exists():
        shutil.rmtree(str(target))
    target.mkdir(parents=True)
    if not requires:
        return
    _run([sys.executable, "-m", "pip", "install", "--target", target, "--platform", PIP_TAG, "--python-version",
          "3.13", "--implementation", "cp", "--only-binary=:all:", "--no-compile"] + list(index_args) + requires)


def build(project: Path, release: bool = False) -> Path:
    if sys.platform != "win32" and not os.environ.get(runtime.ENV_DIST["windows"]):
        raise BuildError("the native Windows app builds on Windows (or set PYXPO_WINDOWS_DIST to a prebuilt shell)")
    return stage(project, release)


class WindowsApp:
    """The running app. A WinUI app has no console, so its output comes through a pipe that a thread copies to
    this terminal. Same wait()/terminate() calls as a Popen."""

    def __init__(self, exe: Path, extras: Optional[Dict[str, str]] = None) -> None:
        env = dict(os.environ)
        env.update(extras or {}, PYXPO_STDIO="1", PYTHONIOENCODING="utf-8")
        print("> " + str(exe))
        self.proc = subprocess.Popen([str(exe)], cwd=str(Path(exe).parent), env=env, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self._echo_thread = threading.Thread(target=self._echo, daemon=True, name="pyxpo-win-log")
        self._echo_thread.start()

    def _echo(self) -> None:
        out = self.proc.stdout
        if out is None:
            return
        for chunk in iter(lambda: out.read1(65536) if hasattr(out, "read1") else out.read(4096), b""):
            sys.stdout.buffer.write(chunk)
            sys.stdout.flush()

    def wait(self) -> int:
        code = self.proc.wait()
        self._echo_thread.join(2)
        return code

    def terminate(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()


def run(exe: Path, extras: Optional[Dict[str, str]] = None) -> WindowsApp:
    return WindowsApp(exe, extras)
