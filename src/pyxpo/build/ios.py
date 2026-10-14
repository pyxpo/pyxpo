"""iOS build: render the Xcode shell, stage Python + app, build with xcodebuild, run on a simulator."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from ..config import load_config, pip_index_args
from .android import BuildError, _run, _skip_runtime_file  # noqa: F401  (shared helpers)

REPO = Path(__file__).resolve().parents[3]
DIST = Path(os.environ.get("PYXPO_IOS_DIST", REPO / "dist" / "ios"))
COMMON = Path(os.environ.get("PYXPO_NATIVE_COMMON", REPO / "native" / "common"))
TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "ios"
WRAP_SCRIPT = Path(__file__).resolve().parent / "ios_wrap.py"

STDLIB_SKIP = ("test", "idlelib", "tkinter", "turtledemo", "ensurepip", "lib2to3", "config-3.13")
TEXT_SUFFIXES = (".yml", ".plist", ".swift", ".sh", ".h", ".m")
# sdk -> (stage slice name, pip platform tag)
PIP_TAGS = {"simulator": "ios_15_0_arm64_iphonesimulator", "device": "ios_15_0_arm64_iphoneos"}


def tool_path(name: str) -> str:
    p = shutil.which(name)
    if not p:
        raise BuildError("%s not found on PATH" % name)
    return p


def find_slice(kind: str) -> Optional[Path]:
    """kind: 'simulator' or 'device'. Returns the xcframework slice dir, or None if not built."""
    xc = DIST / "Python.xcframework"
    if not xc.is_dir():
        return None
    for d in sorted(xc.iterdir()):
        if d.is_dir() and d.name.startswith("ios-") and (d.name.endswith("simulator") == (kind == "simulator")):
            return d
    return None


def render_shell(dest: Path, values: Dict[str, str]) -> None:
    if dest.exists():
        shutil.rmtree(str(dest))
    for src in TEMPLATE.rglob("*"):
        if src.is_dir():
            continue
        out = dest / src.relative_to(TEMPLATE)
        out.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix in TEXT_SUFFIXES:
            text = src.read_text()
            for k, v in values.items():
                text = text.replace("{{%s}}" % k, v)
            out.write_text(text)
        else:
            shutil.copy2(str(src), str(out))
    (dest / "scripts").mkdir(exist_ok=True)
    shutil.copy2(str(WRAP_SCRIPT), str(dest / "scripts" / "ios_wrap.py"))
    (dest / "native").mkdir(exist_ok=True)
    for f in ("pyxpo_bridge.c", "pyxpo_bridge.h", "pyxpo_layout.c", "pyxpo_layout.h"):
        shutil.copy2(str(COMMON / f), str(dest / "native" / f))
    (dest / "Python.xcframework").symlink_to(DIST / "Python.xcframework")


def install_requires(requires: List[str], kind: str, target: Path, index_args: List[str] = ()) -> None:
    if target.exists():
        shutil.rmtree(str(target))
    target.mkdir(parents=True)
    if not requires:
        return
    _run([sys.executable, "-m", "pip", "install", "--target", target, "--platform", PIP_TAGS[kind],
          "--python-version", "3.13", "--implementation", "cp", "--only-binary=:all:", "--no-compile"] + list(index_args) + requires)


def _stage_stdlib(slice_dir: Path, dest: Path, compile_with: Optional[Path]) -> None:
    if dest.exists():
        shutil.rmtree(str(dest))
    src = slice_dir / "lib" / "python3.13"
    shutil.copytree(str(src), str(dest / "lib" / "python3.13"), symlinks=True,
                    ignore=lambda d, names: [n for n in names if n in STDLIB_SKIP or n == "__pycache__"])
    if compile_with and compile_with.is_file():  # read-only bundle: ship .pyc so startup is fast
        subprocess.run([str(compile_with), "-m", "compileall", "-q", "-j0", str(dest / "lib" / "python3.13")],
                       check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _stage_app(project: Path, dest: Path, release: bool) -> None:
    if dest.exists():
        shutil.rmtree(str(dest))
    for sub in ("app", "assets"):
        d = project / sub
        if d.is_dir():
            shutil.copytree(str(d), str(dest / sub), ignore=shutil.ignore_patterns("__pycache__", ".*"))
    pkg = Path(__file__).resolve().parent.parent
    for p in sorted(pkg.rglob("*.py")):
        rel = p.relative_to(pkg)
        if _skip_runtime_file(rel, release):
            continue
        out = dest / "pyxpo" / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(p), str(out))


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", name) or "PyxpoApp"


# -- simulator ------------------------------------------------------------
def pick_simulator(devices_json: dict) -> Optional[Dict[str, str]]:
    """Choose a simulator from `simctl list devices available -j`: booted iPhone, else newest iPhone."""
    cands = []
    for runtime, devs in devices_json.get("devices", {}).items():
        if "iOS" not in runtime:
            continue
        for d in devs:
            if d.get("isAvailable", True) and d.get("name", "").startswith("iPhone"):
                cands.append((d.get("state") == "Booted", runtime, d["name"], d))
    if not cands:
        return None
    cands.sort(key=lambda c: (c[0], c[1], c[2]))
    return cands[-1][3]


def simulator() -> Dict[str, str]:
    out = subprocess.run(["xcrun", "simctl", "list", "devices", "available", "-j"],
                         check=True, capture_output=True, text=True).stdout
    dev = pick_simulator(json.loads(out))
    if dev is None:
        raise BuildError("no iPhone simulator found; install one in Xcode")
    if dev.get("state") != "Booted":
        _run(["xcrun", "simctl", "boot", dev["udid"]])
    # Show the Simulator window when the app exists; a headless simulator is fine without it.
    if subprocess.run(["open", "-Ra", "Simulator"], capture_output=True).returncode == 0:
        subprocess.run(["open", "-a", "Simulator"], check=False)
    return dev


def launch_env(extras: Optional[Dict[str, str]]) -> Dict[str, str]:
    """simctl forwards variables prefixed SIMCTL_CHILD_ to the app (prefix stripped)."""
    env = dict(os.environ)
    for k, v in (extras or {}).items():
        env["SIMCTL_CHILD_" + k] = v
    return env


def launch(udid: str, app_id: str, extras: Optional[Dict[str, str]] = None, console: bool = True) -> "subprocess.Popen":
    cmd = ["xcrun", "simctl", "launch"] + (["--console-pty"] if console else []) + [
        "--terminate-running-process", udid, app_id]
    print("> " + " ".join(cmd))
    return subprocess.Popen(cmd, env=launch_env(extras))


# -- build ----------------------------------------------------------------
def build(project: Path, release: bool = False, kind: str = "simulator") -> Path:
    project = Path(project).resolve()
    cfg = load_config(project)
    name = cfg.get("name", project.name)
    app_id = cfg.get("bundle_id", "com.example.app")
    slice_dir = find_slice(kind)
    if slice_dir is None:
        raise BuildError("no iOS %s CPython in %s; run native/ios/build_cpython.py" % (kind, DIST))
    tool_path("xcodegen")
    product = _safe_name(name)

    stage = project / "build" / "ios"
    shell = stage / "shell"
    render_shell(shell, {"app_name": name, "app_id": app_id, "product_name": product})
    st = shell / "stage"
    host_py = REPO / ".cache" / "Python-3.13.7" / "cross-build" / "build" / "python.exe"
    _stage_stdlib(slice_dir, st / ("python-" + kind), host_py)
    _stage_app(project, st / "app_root", release)
    install_requires(list(cfg.get("requires", [])), kind, st / ("site-" + kind), pip_index_args(cfg, project))

    _run(["xcodegen", "generate", "--spec", shell / "project.yml", "--project", shell], cwd=str(shell))
    sdk = "iphonesimulator" if kind == "simulator" else "iphoneos"
    cfgname = "Release" if release else "Debug"
    cmd = ["xcodebuild", "-project", shell / "PyxpoApp.xcodeproj", "-scheme", "PyxpoApp", "-sdk", sdk,
           "-configuration", cfgname, "-derivedDataPath", shell / "build", "build"]
    if kind == "simulator":
        cmd += ["ARCHS=arm64", "ONLY_ACTIVE_ARCH=YES"]
    _run(cmd)
    app = shell / "build" / "Build" / "Products" / ("%s-%s" % (cfgname, sdk)) / ("%s.app" % product)
    if not app.is_dir():
        raise BuildError("app not produced: %s" % app)
    print("built %s" % app)
    return app


def install_and_run(app: Path, app_id: str, extras: Optional[Dict[str, str]] = None) -> "subprocess.Popen":
    dev = simulator()
    _run(["xcrun", "simctl", "install", dev["udid"], app])
    return launch(dev["udid"], app_id, extras)
