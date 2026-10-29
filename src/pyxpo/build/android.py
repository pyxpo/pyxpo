from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .. import config_plugins, native_config, term
from ..config import app_dirs, load_config, pip_index_args
from ..module_hooks import build_mode
from . import prebuild as prebuild_mod
from . import android_config, app_json, autolink, elfcheck, runtime
from .runtime import BuildError  # noqa: F401  (re-exported)

DIST = runtime.dist_path("android")
COMMON = runtime.native_common()
TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "android"

ABI_TAGS = {"arm64-v8a": "android_24_arm64_v8a", "armeabi-v7a": "android_24_armeabi_v7a", "x86_64": "android_24_x86_64"}
# 32-bit ARM, for phones that run a 32-bit Android (Galaxy M13 5G and many low-cost phones). Unless [tool.pyxpo]
# abis lists it, a build leaves it out with a warning when a requirement has no wheel for it.
OPTIONAL_ABIS = ("armeabi-v7a",)
SO_FOR_JNILIBS = ["libpython3.13.so", "libcrypto_python.so", "libssl_python.so", "libsqlite3_python.so"]
STDLIB_SKIP = ("test", "idlelib", "tkinter", "turtledemo", "ensurepip", "lib2to3", "config-3.13")


def _run(cmd: List[str], quiet: bool = False, **kw) -> None:
    """Run a build command; `quiet` hides its output unless it fails."""
    if quiet:
        kw.update(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    else:
        print("> " + " ".join(str(c) for c in cmd))
    r = subprocess.run([str(c) for c in cmd], **kw)
    if r.returncode != 0:
        if quiet:
            print("> " + " ".join(str(c) for c in cmd) + "\n" + (r.stdout or ""), end="")
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


def find_gradle(native: Optional[Path] = None) -> str:
    """The project's Gradle wrapper (pinned version, downloaded on first use); a pyxpo checkout uses its cached copy."""
    cached = sorted(runtime.REPO.glob(".cache/gradle-*/bin/gradle")) if runtime.is_dev_checkout() else []
    if cached:
        return str(cached[-1])
    if native is not None and (Path(native) / "gradlew").is_file():
        return str(Path(native) / "gradlew")
    g = shutil.which("gradle")
    if g:
        return g
    raise BuildError("gradle not found: run `pyxpo prebuild android` to add the Gradle wrapper, or install Gradle 8")


GEN = "pyxpo-gen"
# Filled by stage(), not render_gen(). The app code is per build type, so `./gradlew assemble` (debug + release in one
# run) cannot pack the debug app into the release APK.
STAGED = ("assets", "jniLibs", "site", "app-debug", "app-release")


def native_dir(project: Path) -> Path:
    """The ejected `android/` folder when `pyxpo prebuild` made one, else a throwaway one under build/."""
    ejected = Path(project) / "android"
    return ejected if prebuild_mod.is_ejected(ejected) else Path(project) / "build" / "android" / "shell"


def properties_text(nc: Dict[str, object], project: Path, abis: List[str]) -> str:
    """Values the user-owned Gradle files read from pyxpo-gen/pyxpo.properties (rewritten on every build)."""
    props = {
        "applicationId": nc["android"]["package"], "name": nc["name"], "scheme": nc["scheme"], "versionName": nc["version"],
        "versionCode": nc["android"]["version_code"], "abis": ",".join(abis), "dist": DIST, "common": COMMON,
        "python": sys.executable,  # runs `pyxpo stage android` when Gradle builds an ejected project directly
    }
    if nc["keystore"]:
        ks = Path(str(nc["keystore"]))
        props["keystore"] = ks if ks.is_absolute() else Path(project) / ks
        props["keyAlias"] = nc["key_alias"]
    return "".join("%s=%s\n" % (k, str(v).replace("\\", "\\\\")) for k, v in props.items())


def render_gen(native: Path, nc: Dict[str, object], project: Path, abis: List[str],
               linked: Optional[autolink.Linked] = None) -> Path:
    """Refreshes the framework-owned `pyxpo-gen/` folder. Never touches anything outside it.
    Files are rendered into a scratch folder, then synced, so a Gradle build already running keeps its inputs."""
    final = native / GEN
    gen = native / (GEN + ".tmp")
    if gen.exists():
        shutil.rmtree(str(gen))
    for rel, data in prebuild_mod.render(TEMPLATE / "gen", {}).items():
        out = gen / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
    (gen / "pyxpo.properties").write_text(properties_text(nc, project, abis))
    autolink.render_android(gen, linked.modules if linked else [])
    mods = config_plugins.load(nc, project)
    android_config.write(gen, nc, project, mods)
    android_config.write_gradle_properties(native, mods, autolink.gradle_properties(linked.modules if linked else []))
    mods.run_dangerous("android", project, native)
    try:
        (native / "local.properties").write_text("sdk.dir=%s\n" % find_sdk())
    except BuildError:
        pass  # the real build reports the missing SDK
    prebuild_mod.sync_tree(gen, final, keep=STAGED)
    return final


def available_abis(requested: Optional[List[str]] = None) -> List[str]:
    """ABIs with a CPython build, fetching them first when they live in the pyxpo cache."""
    runtime.ensure("android", requested, DIST)
    return [a for a in ABI_TAGS if (requested is None or a in requested)
            and (DIST / a / "prefix" / "lib" / "libpython3.13.so").is_file()]


def _cfg_abis(cfg: Dict[str, object]) -> Optional[List[str]]:
    v = cfg.get("abis")
    return [str(a) for a in v] if isinstance(v, (list, tuple)) and v else None


def _write_user(native: Path, rendered: Dict[str, bytes]) -> None:
    for rel, data in rendered.items():
        (native / rel).parent.mkdir(parents=True, exist_ok=True)
        (native / rel).write_bytes(data)
    _make_gradlew_executable(native)


def _make_gradlew_executable(native: Path) -> None:
    w = native / "gradlew"
    if w.is_file():
        w.chmod(w.stat().st_mode | 0o111)


MOVED_STATE = (".gradle", "build", "app/build", "app/.cxx")


def _drop_moved_gradle_state(native: Path, inside_gradle: bool = False) -> None:
    """Gradle keeps absolute paths in .gradle/ and build/. After the project folder moves, AGP's incremental dexing
    mixes old and new paths ("is located outside the root directory"). The path is recorded in .gradle/ (it goes
    when the state goes); when it differs, the stale state is removed. A running Gradle has it open already, so the
    Gradle stage task only says what to run."""
    state = native / ".gradle"
    marker = state / "pyxpo-root"
    here = str(native.resolve())
    old = marker.read_text().strip() if marker.is_file() else here
    if old != here:
        if inside_gradle:
            term.warn("this project moved from %s; if the build fails, run `./gradlew --stop`, delete android/.gradle "
                      "and android/app/build, then build again" % old)
            return
        term.warn("this project moved from %s: removing stale Gradle state" % old)
        for rel in MOVED_STATE:
            shutil.rmtree(str(native / rel), ignore_errors=True)
        for b in sorted((native / GEN).glob("*/build")):
            shutil.rmtree(str(b), ignore_errors=True)
    if native.is_dir():
        state.mkdir(exist_ok=True)
        marker.write_text(here + "\n")


def prebuild(project: Path, clean: bool = False) -> Path:
    """Ejects `<project>/android`: user-owned files are written once (edited ones are kept), `pyxpo-gen/` is refreshed."""
    project = Path(project).resolve()
    cfg = load_config(project)
    nc = native_config.resolve(cfg, project)
    linked = autolink.link(cfg, project)  # fail on module errors before touching the project
    dest = project / "android"
    if clean and dest.exists():
        shutil.rmtree(str(dest))
    rendered = prebuild_mod.render(TEMPLATE / "user", {})
    rendered[".gitignore"] = ("%s/\n%s.tmp/\n.gradle/\nbuild/\napp/build/\napp/.cxx/\nlocal.properties\n*.pyxpo-new\n" % (GEN, GEN)).encode()
    from .. import __version__
    for action, rel in prebuild_mod.apply(rendered, dest, __version__):
        if action == "conflict":
            term.warn("kept your edited android/%s; new version saved as android/%s.pyxpo-new" % (rel, rel))
    _make_gradlew_executable(dest)
    _drop_moved_gradle_state(dest)
    render_gen(dest, nc, project, available_abis(_cfg_abis(cfg)), linked)
    return dest


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
    lines = ["  %s (alignment %d)" % (_rel(p, site, jni_abi), a)
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
    if rel.parts[0] in ("templates", "build") or rel.name in ("cli.py", "__main__.py") or "__pycache__" in rel.parts:
        return True
    if rel.parts[0] == "dev" and (release or rel.name == "server.py"):
        return True
    return False


def adb_path() -> str:
    return str(find_sdk() / "platform-tools" / "adb")


EMULATOR_BOOT_TIMEOUT = 300.0


def parse_devices(out: str) -> List[Tuple[str, str]]:
    """(serial, state) pairs from `adb devices` output; state is device, offline, unauthorized, ..."""
    rows = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            rows.append((parts[0], parts[1]))
    return rows


def _devices(adb: str) -> List[Tuple[str, str]]:
    r = subprocess.run([adb, "devices"], capture_output=True, text=True)
    return parse_devices(r.stdout) if r.returncode == 0 else []


def list_avds(sdk: Path) -> List[str]:
    emu = sdk / "emulator" / "emulator"
    if not emu.is_file():
        return []
    r = subprocess.run([str(emu), "-list-avds"], capture_output=True, text=True)
    # newer emulators print INFO lines here too; AVD names never contain spaces
    return [l.strip() for l in r.stdout.splitlines() if l.strip() and " " not in l.strip() and "|" not in l]


def _start_emulator(sdk: Path, avd: str, adb: str) -> str:
    """Boot `avd` in the background (it outlives this run) and wait until Android finished booting."""
    log = Path(tempfile.gettempdir()) / ("pyxpo-emulator-%s.log" % avd)
    extra = os.environ.get("PYXPO_EMULATOR_ARGS", "").split()
    print("no Android device connected; starting emulator %s (log: %s)" % (avd, log), flush=True)
    with open(str(log), "wb") as f:
        proc = subprocess.Popen([str(sdk / "emulator" / "emulator"), "-avd", avd] + extra, stdout=f, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, start_new_session=True)
    deadline = time.time() + EMULATOR_BOOT_TIMEOUT
    while time.time() < deadline:
        if proc.poll() is not None:
            raise BuildError("emulator %s exited (code %s); see %s. Extra flags go in PYXPO_EMULATOR_ARGS "
                             "(e.g. -no-audio)" % (avd, proc.returncode, log))
        for serial, state in _devices(adb):
            if serial.startswith("emulator-") and state == "device":
                r = subprocess.run([adb, "-s", serial, "shell", "getprop", "sys.boot_completed"],
                                   capture_output=True, text=True)
                if r.stdout.strip() == "1":
                    print("emulator %s ready (%s)" % (avd, serial), flush=True)
                    return serial
        time.sleep(2)
    raise BuildError("emulator %s did not finish booting in %ds; see %s" % (avd, EMULATOR_BOOT_TIMEOUT, log))


def ensure_device(want: Optional[str] = None) -> str:
    """Pick the device to install on and pin it in ANDROID_SERIAL so every later adb call targets it.

    `want` (--device) is a serial or an AVD name. With nothing connected, boots an emulator: `want` when it names
    an AVD, else the only AVD (or the first, listed). Several devices and no `want` is an error naming them.
    """
    want = want or os.environ.get("ANDROID_SERIAL") or None
    sdk, adb = find_sdk(), adb_path()
    devs = _devices(adb)
    ready = [s for s, st in devs if st == "device"]
    if want and want in ready:
        serial = want
    elif want and any(s == want for s, _ in devs):
        state = dict(devs)[want]
        raise BuildError("device %s is %s; %s" % (want, state, _STATE_HINT.get(state, "reconnect it")))
    elif not want and len(ready) == 1:
        serial = ready[0]
    elif not want and len(ready) > 1:
        raise BuildError("several Android devices connected (%s); pick one with --device SERIAL" % ", ".join(ready))
    else:
        bad = [(s, st) for s, st in devs if st != "device"]
        if not want and bad:  # a phone is plugged in but not usable: say why instead of booting an emulator
            s, st = bad[0]
            raise BuildError("device %s is %s; %s" % (s, st, _STATE_HINT.get(st, "reconnect it")))
        avds = list_avds(sdk)
        if want and want not in avds:
            raise BuildError("no connected device or AVD named %r (devices: %s; AVDs: %s)" % (
                want, ", ".join(ready) or "none", ", ".join(avds) or "none"))
        if not avds:
            raise BuildError("no Android device connected and no emulator (AVD) to start; plug in a phone with "
                             "USB debugging on, or create an AVD in Android Studio (Device Manager)")
        serial = _start_emulator(sdk, want or avds[0], adb)
    os.environ["ANDROID_SERIAL"] = serial
    return serial


_STATE_HINT = {
    "unauthorized": "unlock the phone and accept the \"Allow USB debugging\" prompt",
    "offline": "replug the cable, or run `adb kill-server` and try again",
    "no": "check the USB cable and that USB debugging is on",
}


def launch(app_id: str, extras: Optional[Dict[str, str]] = None) -> None:
    # -S: a running instance would ignore the launch extras, so stop it first
    cmd = [adb_path(), "shell", "am", "start", "-S", "-n", "%s/dev.pyxpo.runtime.MainActivity" % app_id]
    for k, v in (extras or {}).items():
        cmd += ["--es", k, v]
    _run(cmd)


def stage(native: Path, project: Path, cfg: Dict[str, object], release: bool, abis: List[str]) -> None:
    """Refreshes pyxpo-gen/ (config, runtime, Python, app, site-packages). User-owned files stay untouched."""
    nc = native_config.resolve(cfg, project)
    if prebuild_mod.is_ejected(native):
        autolink.check_android_wiring(native)
    linked = autolink.link(cfg, project)
    gen = render_gen(native, nc, project, abis, linked)
    jni = gen / "jniLibs"
    if jni.exists():
        shutil.rmtree(str(jni))
    assets = gen / "assets" / "pyxpo"
    assets.mkdir(parents=True, exist_ok=True)
    for old in ("app.zip", "manifest.txt"):  # older pyxpo kept the app in main assets
        if (assets / old).exists():
            (assets / old).unlink()
    explicit = _cfg_abis(cfg) is not None
    kept = []
    for abi in abis:
        prefix = DIST / abi / "prefix"
        site = gen / "site" / abi
        try:
            install_requires(list(cfg.get("requires", [])), abi, site, pip_index_args(cfg, project))
        except BuildError:
            if explicit or abi not in OPTIONAL_ABIS:
                raise
            shutil.rmtree(str(site), ignore_errors=True)
            term.warn("left out %s: a requirement has no %s wheel, so phones with a 32-bit Android cannot install "
                      "this app. List abis in [tool.pyxpo] to make this an error." % (abi, ABI_TAGS[abi]))
            continue
        kept.append(abi)
        _zip_tree(assets / ("stdlib-%s.zip" % abi), prefix / "lib" / "python3.13",
                  arcprefix="lib/python3.13/", skip=STDLIB_SKIP)
        (jni / abi).mkdir(parents=True)
        _check_16kb(site, jni / abi, abi, bool(cfg.get("allow_4kb_libs", False)))
        _zip_tree(assets / ("site-%s.zip" % abi), site)
        for so in SO_FOR_JNILIBS:
            shutil.copy2(str(prefix / "lib" / so), str(jni / abi / so))
    if kept != abis:
        (gen / "pyxpo.properties").write_text(properties_text(nc, project, kept))
    for old in list(assets.glob("stdlib-*.zip")) + list(assets.glob("site-*.zip")):
        if old.stem.split("-", 1)[1] not in kept:  # an ABI an earlier build had
            old.unlink()
    variant = gen / ("app-release" if release else "app-debug") / "pyxpo"
    variant.mkdir(parents=True, exist_ok=True)
    app_zip = variant / "app.zip"
    with zipfile.ZipFile(str(app_zip), "w", zipfile.ZIP_DEFLATED) as z:
        for sub in app_dirs(cfg, project):
            d = project / sub
            for p in sorted(d.rglob("*")) if d.is_dir() else []:
                rel = p.relative_to(project)
                if p.is_file() and ships_in_app(rel):
                    z.write(str(p), str(rel))
        # framework runtime (no CLI/templates/build tooling)
        pkg = Path(__file__).resolve().parent.parent
        for p in sorted(pkg.rglob("*.py")):
            rel = p.relative_to(pkg)
            if _skip_runtime_file(rel, release):
                continue
            z.write(str(p), "pyxpo/" + str(rel))
        for src, arc in autolink.python_files(linked.modules):  # linked module packages live outside pyxpo
            z.write(str(src), arc)
        z.writestr("pyxpo/" + app_json.NAME, app_json.dumps(nc))
    h = hashlib.sha256()
    for p in sorted(assets.glob("*.zip")) + [app_zip]:
        h.update(p.name.encode())
        h.update(p.read_bytes())
    (variant / "manifest.txt").write_text(h.hexdigest()[:16])


def ships_in_app(rel: Path) -> bool:
    """Whether a file under app/ or assets/ goes into app.zip. Dotfiles (.env, .env.local, .git, .DS_Store) never
    ship, as on iOS, web and Windows."""
    return "__pycache__" not in rel.parts and not any(x.startswith(".") for x in rel.parts)


def stage_project(project: Path, release: bool = False) -> None:
    """`pyxpo stage android`: what `./gradlew assemble*` or Android Studio runs before building an ejected project."""
    project = Path(project).resolve()
    cfg = load_config(project, build_mode(release))
    abis = available_abis(_cfg_abis(cfg))
    if not abis:
        raise BuildError("no Android CPython build in %s (set PYXPO_ANDROID_DIST, or see `pyxpo doctor`)" % DIST)
    _drop_moved_gradle_state(native_dir(project), inside_gradle=True)
    stage(native_dir(project), project, cfg, release, abis)


def build(project: Path, release: bool = False, install: bool = False, run: bool = False,
          device: Optional[str] = None) -> Path:
    project = Path(project).resolve()
    cfg = load_config(project, build_mode(release))
    nc = native_config.resolve(cfg, project)
    abis = available_abis(_cfg_abis(cfg))
    if not abis:
        raise BuildError("no Android CPython build in %s (set PYXPO_ANDROID_DIST, or see `pyxpo doctor`)" % DIST)
    sdk = find_sdk()
    if find_ndk(sdk) is None:
        raise BuildError("NDK 27.3.13750724 missing; sdkmanager 'ndk;27.3.13750724'")

    if install or run:  # before the slow Gradle build: a missing or unusable device fails fast
        ensure_device(device)

    native = native_dir(project)
    if not prebuild_mod.is_ejected(native):  # implicit prebuild: a disposable project nobody edits
        if native.exists():
            shutil.rmtree(str(native))
        _write_user(native, prebuild_mod.render(TEMPLATE / "user", {}))
    _drop_moved_gradle_state(native)
    stage(native, project, cfg, release, abis)

    # PYXPO_STAGED: the app is staged already, so the Gradle stage task (for direct ./gradlew builds) skips itself
    _run([find_gradle(native), "-p", native, "--console=plain", "assembleRelease" if release else "assembleDebug"],
         env=dict(os.environ, ANDROID_HOME=str(sdk), PYXPO_STAGED="1"))
    outdir = native / "app" / "build" / "outputs" / "apk" / ("release" if release else "debug")
    apk = outdir / ("app-release.apk" if release else "app-debug.apk")
    if release and not apk.is_file() and (outdir / "app-release-unsigned.apk").is_file():
        apk = outdir / "app-release-unsigned.apk"  # an ejected build.gradle.kts from before debug-key signing
    if not apk.is_file():
        raise BuildError("apk not produced: %s" % apk)
    print("built %s" % apk)
    if release and not nc["keystore"]:
        term.warn("signed with the debug key: fine for testing on a phone; set keystore in [tool.pyxpo.android] for Google Play")
    if install or run:
        _run([adb_path(), "install", "-r", apk])
        if run:
            launch(str(nc["android"]["package"]))
    return apk
