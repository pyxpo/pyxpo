from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

from ..config import load_config, pip_index_args
from . import elfcheck

REPO = Path(__file__).resolve().parents[3]
DIST = Path(os.environ.get("PYXPO_ANDROID_DIST", REPO / "dist" / "android"))
COMMON = Path(os.environ.get("PYXPO_NATIVE_COMMON", REPO / "native" / "common"))
TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "android"

ABI_TAGS = {"arm64-v8a": "android_24_arm64_v8a", "x86_64": "android_24_x86_64"}
SO_FOR_JNILIBS = ["libpython3.13.so", "libcrypto_python.so", "libssl_python.so", "libsqlite3_python.so"]
STDLIB_SKIP = ("test", "idlelib", "tkinter", "turtledemo", "ensurepip", "lib2to3", "config-3.13")


class BuildError(Exception):
    pass


def _run(cmd: List[str], **kw) -> None:
    print("> " + " ".join(str(c) for c in cmd))
    r = subprocess.run([str(c) for c in cmd], **kw)
    if r.returncode != 0:
        raise BuildError("command failed (%d): %s" % (r.returncode, cmd[0]))


def find_sdk() -> Path:
    for var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        if os.environ.get(var):
            return Path(os.environ[var])
    guess = Path.home() / "Library" / "Android" / "sdk"
    if not guess.is_dir():
        guess = Path.home() / "Android" / "Sdk"
    if guess.is_dir():
        return guess
    raise BuildError("Android SDK not found; set ANDROID_HOME")


def find_ndk(sdk: Path) -> Optional[Path]:
    if os.environ.get("ANDROID_NDK_HOME"):
        return Path(os.environ["ANDROID_NDK_HOME"])
    pinned = sdk / "ndk" / "27.3.13750724"
    return pinned if pinned.is_dir() else None


def find_gradle() -> str:
    g = shutil.which("gradle")
    if g:
        return g
    cached = sorted(REPO.glob(".cache/gradle-*/bin/gradle"))
    if cached:
        return str(cached[-1])
    raise BuildError("gradle not found; install it or put it on PATH")


def render_shell(dest: Path, values: Dict[str, str]) -> None:
    if dest.exists():
        shutil.rmtree(str(dest))
    for src in TEMPLATE.rglob("*"):
        if src.is_dir():
            continue
        out = dest / src.relative_to(TEMPLATE)
        out.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix in (".kts", ".xml", ".properties", ".c", ".kt", ".txt"):
            text = src.read_text()
            for k, v in values.items():
                text = text.replace("{{%s}}" % k, v)
            out.write_text(text)
        else:
            shutil.copy2(str(src), str(out))


def _zip_tree(zpath: Path, root: Path, arcprefix: str = "", skip=()) -> None:
    zpath.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(zpath), "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(root.rglob("*")):
            rel = p.relative_to(root)
            if p.is_dir() or "__pycache__" in rel.parts or any(part in skip for part in rel.parts):
                continue
            z.write(str(p), arcprefix + str(rel))


def install_requires(requires: List[str], abi: str, target: Path, index_args: List[str] = ()) -> None:
    if target.exists():
        shutil.rmtree(str(target))
    target.mkdir(parents=True)
    if not requires:
        return
    _run([sys.executable, "-m", "pip", "install", "--target", target, "--platform", ABI_TAGS[abi],
          "--python-version", "3.13", "--implementation", "cp", "--only-binary=:all:", "--no-compile"] + list(index_args) + requires)


def _rel(p: Path, *roots: Path) -> str:
    for r in roots:
        try:
            return str(p.relative_to(r))
        except ValueError:
            pass
    return p.name


def _check_16kb(site: Path, jni_abi: Path, abi: str, allow: bool) -> None:
    """Android 15+ devices with 16 KB pages cannot load .so files aligned to 4 KB."""
    bad = elfcheck.find_unaligned([site, jni_abi])
    if not bad:
        return
    lines = ["  %s (p_align=%d)" % (_rel(p, site, jni_abi), a)
             for p, a in bad[:10]]
    msg = ("%d native libs for %s are not 16 KB aligned and crash on 16 KB-page devices "
           "(Pixel 8+ on Android 15+, required by Google Play):\n%s%s\n"
           "Use wheels built with -Wl,-z,max-page-size=16384 (pyxpo-wheels), or set allow_4kb_libs = true "
           "in [tool.pyxpo] to build anyway for 4 KB devices only." % (
               len(bad), abi, "\n".join(lines), "\n  ..." if len(bad) > 10 else ""))
    if not allow:
        raise BuildError(msg)
    print("warning: " + msg)


def _skip_runtime_file(rel: Path, release: bool) -> bool:
    """Files left out of app.zip: tooling always; the hot-reload package in release builds."""
    if rel.parts[0] in ("templates", "build") or rel.name == "cli.py" or "__pycache__" in rel.parts:
        return True
    if rel.parts[0] == "dev" and (release or rel.name == "server.py"):
        return True
    return False


def adb_path() -> str:
    return str(find_sdk() / "platform-tools" / "adb")


def launch(app_id: str, extras: Optional[Dict[str, str]] = None) -> None:
    _run([adb_path(), "shell", "am", "force-stop", app_id])  # a running instance would ignore the launch extras
    cmd = [adb_path(), "shell", "am", "start", "-n", "%s/dev.pyxpo.runtime.MainActivity" % app_id]
    for k, v in (extras or {}).items():
        cmd += ["--es", k, v]
    _run(cmd)


def build(project: Path, release: bool = False, install: bool = False, run: bool = False) -> Path:
    project = Path(project).resolve()
    cfg = load_config(project)
    name = cfg.get("name", project.name)
    app_id = cfg.get("bundle_id", "com.example.app")
    abis = [a for a in ABI_TAGS if (DIST / a / "prefix" / "lib" / "libpython3.13.so").is_file()]
    if not abis:
        raise BuildError("no CPython build in %s; run native/android/build_cpython.py" % DIST)
    sdk = find_sdk()
    if find_ndk(sdk) is None:
        raise BuildError("NDK 27.3.13750724 missing; sdkmanager 'ndk;27.3.13750724'")

    stage = project / "build" / "android"
    shell = stage / "shell"
    jni = stage / "jniLibs"
    values = {
        "app_name": name, "app_id": app_id, "common": str(COMMON), "dist": str(DIST),
        "dist_jnilibs": str(jni), "abis": ", ".join('"%s"' % a for a in abis),
    }
    render_shell(shell, values)
    (shell / "local.properties").write_text("sdk.dir=%s\n" % sdk)

    assets = shell / "app" / "src" / "main" / "assets" / "pyxpo"
    assets.mkdir(parents=True, exist_ok=True)
    if jni.exists():
        shutil.rmtree(str(jni))
    for abi in abis:
        prefix = DIST / abi / "prefix"
        _zip_tree(assets / ("stdlib-%s.zip" % abi), prefix / "lib" / "python3.13",
                  arcprefix="lib/python3.13/", skip=STDLIB_SKIP)
        site = stage / "site" / abi
        install_requires(list(cfg.get("requires", [])), abi, site, pip_index_args(cfg, project))
        (jni / abi).mkdir(parents=True)
        _check_16kb(site, jni / abi, abi, bool(cfg.get("allow_4kb_libs", False)))
        _zip_tree(assets / ("site-%s.zip" % abi), site)
        for so in SO_FOR_JNILIBS:
            shutil.copy2(str(prefix / "lib" / so), str(jni / abi / so))
    app_zip = assets / "app.zip"
    with zipfile.ZipFile(str(app_zip), "w", zipfile.ZIP_DEFLATED) as z:
        for sub in ("app", "assets"):
            d = project / sub
            for p in sorted(d.rglob("*")) if d.is_dir() else []:
                if p.is_file() and "__pycache__" not in p.parts:
                    z.write(str(p), str(p.relative_to(project)))
        # framework runtime (no CLI/templates/build tooling)
        pkg = Path(__file__).resolve().parent.parent
        for p in sorted(pkg.rglob("*.py")):
            rel = p.relative_to(pkg)
            if _skip_runtime_file(rel, release):
                continue
            z.write(str(p), "pyxpo/" + str(rel))
    h = hashlib.sha256()
    for p in sorted(assets.glob("*.zip")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    (assets / "manifest.txt").write_text(h.hexdigest()[:16])

    _run([find_gradle(), "-p", shell, "--console=plain", "assembleRelease" if release else "assembleDebug"],
         env=dict(os.environ, ANDROID_HOME=str(sdk)))
    apk = shell / "app" / "build" / "outputs" / "apk" / ("release" if release else "debug") / (
        "app-release-unsigned.apk" if release else "app-debug.apk")
    if not apk.is_file():
        raise BuildError("apk not produced: %s" % apk)
    print("built %s" % apk)
    if install or run:
        _run([adb_path(), "install", "-r", apk])
        if run:
            launch(app_id)
    return apk
