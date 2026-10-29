from __future__ import annotations

import argparse
import errno
import json
import os
import re
import runpy
import secrets
import shutil
import sys
import threading
from pathlib import Path
from typing import Dict, List, Optional

from . import native_config
from .config import load_config, set_requires

TEMPLATE = Path(__file__).parent / "templates" / "app"


def cmd_create(args: argparse.Namespace) -> int:
    name = args.name
    if not re.match(r"^[A-Za-z][A-Za-z0-9_-]*$", name):
        print("error: invalid project name %r (letters, digits, - and _ only)" % name, file=sys.stderr)
        return 2
    dest = Path(args.dir or ".") / name
    if dest.exists():
        print("error: %s already exists" % dest, file=sys.stderr)
        return 2
    ident = re.sub(r"[^a-z0-9]", "", name.lower())
    for src in TEMPLATE.rglob("*.tmpl"):
        rel = src.relative_to(TEMPLATE)
        out = dest / str(rel)[: -len(".tmpl")]
        if out.name == "gitignore":
            out = out.with_name(".gitignore")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(src.read_text().replace("{{name}}", name).replace("{{ident}}", ident))
    (dest / "assets").mkdir(exist_ok=True)
    print("created %s\n  cd %s && pyxpo run desktop\n  native changes: pyxpo prebuild  (creates editable android/ and ios/)" % (dest, name))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    if args.target == "android":
        return _android(args, run=True)
    if args.target == "ios":
        return _ios(args, run=True)
    if args.target == "web":
        return _web(args, run=True)
    if args.target != "desktop":
        print("pyxpo run %s: not yet implemented (milestone 3)" % args.target, file=sys.stderr)
        return 2
    if not getattr(args, "preview", False) and _native_windows_available():
        return _windows(args, run=True)
    if not getattr(args, "preview", False) and _native_desktop_available():
        return _ios(args, run=True, kind="catalyst")
    project = Path(args.dir or ".").resolve()
    try:
        cfg = load_config(project)
    except (FileNotFoundError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    os.environ["PYXPO_TARGET"] = "desktop"
    os.environ.setdefault("PYXPO_APP_NAME", str(cfg.get("name") or project.name))
    from .app_config.resolve import MODULE_DATA
    from .module_hooks import DATA_ENV
    os.environ[DATA_ENV] = json.dumps(cfg.get(MODULE_DATA) or {})  # no staged _app_config.json in this process
    sys.path.insert(0, str(project))
    if not getattr(args, "no_reload", False):
        from .component import enable_registry

        token = secrets.token_hex(16)
        try:
            dev = _dev_server(args, project, token)
        except OSError as e:
            print("hot reload off: %s" % e, file=sys.stderr)
        else:
            dev.start()
            os.environ["PYXPO_DEV_URL"], os.environ["PYXPO_DEV_TOKEN"] = dev.url, token
            enable_registry(True)
    runpy.run_module("pyxpo.router.entry", run_name="__main__")
    return 0


def _dev_port(args: argparse.Namespace, project: Path) -> int:
    if getattr(args, "port", None):
        return int(args.port)
    return int(load_config(project).get("dev_port", 8765))


DEV_PORT_TRIES = 20


def _dev_server(args: argparse.Namespace, project: Path, token: str):
    """The hot reload server on the dev port. When that port is taken (often another `pyxpo run`, say Android and iOS
    side by side) and --port was not given, the next free port: the app gets the URL, so any port works."""
    from .dev.server import DevServer

    port = _dev_port(args, project)
    tries = 1 if getattr(args, "port", None) or port == 0 else DEV_PORT_TRIES
    for p in range(port, port + tries):
        try:
            dev = DevServer(str(project), p, token)
        except OSError as e:
            if e.errno != errno.EADDRINUSE:
                raise
            continue
        if p != port:
            print("dev port %d is in use (another `pyxpo run`?); using %d" % (port, p), flush=True)
        return dev
    raise OSError(errno.EADDRINUSE, "dev port %d%s is in use" % (port, "" if tries == 1 else "-%d" % (port + tries - 1)))


def _port_error(e: OSError) -> str:
    if e.errno == errno.EADDRINUSE:
        return "error: %s; stop the other `pyxpo run`, pass a free --port N, or use --no-reload" % e.strerror
    return "error: %s" % e


def _android(args: argparse.Namespace, run: bool) -> int:
    from .build import android as droid

    BuildError, build = droid.BuildError, droid.build
    project = Path(args.dir or ".").resolve()
    reload_on = run and not getattr(args, "no_reload", False)
    try:
        build(project, release=getattr(args, "release", False), install=run, run=run and not reload_on,
              device=getattr(args, "device", None))
        if reload_on:
            _android_dev(droid, project, args)
    except (BuildError, FileNotFoundError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    except OSError as e:
        print(_port_error(e), file=sys.stderr)
        return 1
    return 0


ANDROID_DEV_CONNECT_TIMEOUT = 30.0
ANDROID_DEV_RELAUNCHES = 2


def _android_dev(droid, project: Path, args: argparse.Namespace) -> None:
    """Start the dev server, reverse the port to the device, launch with dev extras, serve until Ctrl-C."""
    cfg = load_config(project)
    token = secrets.token_hex(16)
    dev = _dev_server(args, project, token)
    adb = droid.adb_path()
    port = str(dev.port)
    droid._run([adb, "reverse", "tcp:" + port, "tcp:" + port])
    app_id = native_config.resolve(cfg, project)["android"]["package"]
    extras = {"pyxpo_dev_url": dev.url, "pyxpo_dev_token": token}
    try:
        dev.start()
        droid.launch(app_id, extras)
        print("hot reload on %s; edit app/ files, Ctrl-C to stop" % dev.url, flush=True)
        # Android 14+ relaunches an app that was updated while open (System UI's package-update flow), and that
        # relaunch carries no extras, so the app starts without the dev URL. Relaunch until the client connects.
        for _ in range(ANDROID_DEV_RELAUNCHES):
            if dev.polled.wait(ANDROID_DEV_CONNECT_TIMEOUT):
                break
            print("app has not connected to the dev server; relaunching it with hot reload", file=sys.stderr, flush=True)
            droid.launch(app_id, extras)
        dev.serve_forever()
    finally:
        droid._run([adb, "reverse", "--remove", "tcp:" + port])


def _native_desktop_available() -> bool:
    """The native desktop app is the iOS shell built for Mac Catalyst: needs macOS, Xcode and a Catalyst CPython."""
    if sys.platform != "darwin" or os.environ.get("PYXPO_RENDERER"):
        return False
    from .build import ios

    return ios.find_slice("catalyst") is not None


def _native_windows_available() -> bool:
    """The native Windows app needs Windows and the prebuilt shell (dist/windows or PYXPO_WINDOWS_DIST)."""
    if sys.platform != "win32" or os.environ.get("PYXPO_RENDERER"):
        return False
    from .build import windows

    return windows.shell_available()


def _windows(args: argparse.Namespace, run: bool) -> int:
    from .build import windows

    project = Path(args.dir or ".").resolve()
    try:
        exe = windows.build(project, release=getattr(args, "release", False))
        if not run:
            return 0
        return _serve_desktop_app(args, project, lambda extras: windows.run(exe, extras))
    except (windows.BuildError, FileNotFoundError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    except OSError as e:
        print(_port_error(e), file=sys.stderr)
        return 1


def _serve_desktop_app(args: argparse.Namespace, project: Path, start) -> int:
    """Starts a desktop app process with hot reload (unless --no-reload); serves until the window closes or Ctrl-C."""
    extras: Dict[str, str] = {}
    dev = None
    if not getattr(args, "no_reload", False):
        token = secrets.token_hex(16)
        dev = _dev_server(args, project, token)
        extras = {"PYXPO_DEV_URL": dev.url, "PYXPO_DEV_TOKEN": token}
    proc = start(extras)
    try:
        if dev:
            # Closing the window ends the process: stop serving then too, not only on Ctrl-C.
            threading.Thread(target=lambda: (proc.wait(), dev._stop.set()), daemon=True).start()
            print("hot reload on %s; edit app/ files, Ctrl-C to stop" % dev.url, flush=True)
            dev.serve_forever()
        else:
            proc.wait()
    finally:
        proc.terminate()
    return 0


def _ios(args: argparse.Namespace, run: bool, kind: str = "simulator") -> int:
    from .build import ios

    project = Path(args.dir or ".").resolve()
    try:
        cfg = load_config(project)
        app_id = native_config.resolve(cfg, project)["ios"]["bundle_id"]
        app = ios.build(project, release=getattr(args, "release", False), kind=kind)
        if not run:
            return 0
        extras = {}
        dev = None
        if not getattr(args, "no_reload", False):
            token = secrets.token_hex(16)
            dev = _dev_server(args, project, token)
            extras = {"PYXPO_DEV_URL": dev.url, "PYXPO_DEV_TOKEN": token}
        proc = (ios.run_mac(app, extras) if kind == "catalyst"
                else ios.install_and_run(app, app_id, extras, getattr(args, "device", None)))
        try:
            if dev and kind == "catalyst":
                # Closing the Mac window ends the process: stop serving then too, not only on Ctrl-C.
                threading.Thread(target=lambda: (proc.wait(), dev._stop.set()), daemon=True).start()
            if dev:
                print("hot reload on %s; edit app/ files, Ctrl-C to stop" % dev.url, flush=True)
                dev.serve_forever()
            else:
                proc.wait()
        finally:
            proc.terminate()
    except (ios.BuildError, FileNotFoundError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    except OSError as e:
        print(_port_error(e), file=sys.stderr)
        return 1
    return 0


def _web(args: argparse.Namespace, run: bool) -> int:
    """Static single page app in build/web/; `run` serves it with SPA fallback and reloads open pages on change."""
    from .build import web
    from .build.android import BuildError

    project = Path(args.dir or ".").resolve()
    try:
        if not run:
            web.build(project, release=getattr(args, "release", False), base=args.base)
            return 0
        web.serve(project, port=args.port or 8000, base=args.base, open_browser=not args.no_open,
                  devtools=not args.no_devtools)
    except (BuildError, OSError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    if args.target == "android":
        return _android(args, run=False)
    if args.target == "ios":
        return _ios(args, run=False)
    if args.target == "desktop":
        if sys.platform == "win32":
            return _windows(args, run=False)
        return _ios(args, run=False, kind="catalyst")
    if args.target == "web":
        return _web(args, run=False)
    print("pyxpo build %s: not yet implemented (milestone 3)" % args.target, file=sys.stderr)
    return 2


def cmd_prebuild(args: argparse.Namespace) -> int:
    """Eject editable android/ and ios/ projects into the project root (like `expo prebuild`)."""
    from .build import android as droid, ios

    project = Path(args.dir or ".").resolve()
    targets = ["android", "ios"] if args.target == "all" else [args.target]
    if args.clean and not args.yes:
        print("--clean deletes %s and loses your native edits." % ", ".join(t + "/" for t in targets))
        if sys.stdin.isatty() and input("continue? [y/N] ").strip().lower() != "y":
            return 1
        if not sys.stdin.isatty():
            print("error: pass --yes to confirm in a non-interactive shell", file=sys.stderr)
            return 2
    from . import term

    kinds = {"android": "Gradle project", "ios": "Xcode project"}
    try:
        for t in targets:
            existed = (project / t).exists()
            (droid if t == "android" else ios).prebuild(project, clean=args.clean)
            extra = " (PyxpoApp.xcodeproj)" if t == "ios" and (project / "ios" / "PyxpoApp.xcodeproj").exists() else ""
            term.ok("%s %s %s/%s" % ("Updated" if existed else "Created", kinds[t], t, extra))
    except (ios.BuildError, FileNotFoundError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    term.ok(term.bold("Finished prebuild"))
    steps = []
    for t in targets:
        steps.append(("pyxpo run %s" % t, "build and launch in debug"))
    if "android" in targets:
        steps.append(("cd android && ./gradlew assembleRelease", "release APK"))
    if "ios" in targets and (project / "ios" / "PyxpoApp.xcodeproj").exists():
        steps.append(("open ios/PyxpoApp.xcodeproj", "build, sign and archive in Xcode"))
    print("\n" + term.bold("Next steps"))
    width = max(len(s) for s, _ in steps)
    for s, hint in steps:
        term.item(s, hint, width)
    print("\n" + term.dim("%s %s yours: edit and commit. Re-run `pyxpo prebuild` after changing [tool.pyxpo];\n"
                          "files you edited are kept and new versions are saved as *.pyxpo-new."
                          % (" and ".join(t + "/" for t in targets), "is" if len(targets) == 1 else "are")))
    return 0


def cmd_stage(args: argparse.Namespace) -> int:
    """Refresh pyxpo-gen/ (app code, runtime, packages) in an ejected project. Gradle and Xcode call this."""
    from .build import android as droid, ios

    project = Path(args.dir or ".").resolve()
    try:
        if args.target == "android":
            droid.stage_project(project, release=args.release)
        else:
            ios.stage_project(project, release=args.release, kind=args.kind)
    except (ios.BuildError, FileNotFoundError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    print("staged %s app" % args.target)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    def row(label: str, found: Optional[str]) -> None:
        print("  %-14s %s" % (label, found or "not found"))

    print("python      %s" % sys.version.split()[0])
    print("toolchains:")
    for tool in ("adb", "java", "gradle", "cmake", "xcodebuild", "xcrun", "xcodegen"):
        row(tool, shutil.which(tool))
    for var in ("ANDROID_HOME", "ANDROID_NDK_HOME"):
        row(var, os.environ.get(var))
    from .build import runtime

    st = runtime.status()
    print("runtime %s (cache %s):" % (st["runtime"], st["cache"]))
    for plat, info in st["platforms"].items():
        for item, state in info["items"].items():
            row("%s" % item, "%s [%s]" % (state, info["source"]))
    probe = runtime.cache_root()
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    print("  free disk     %.1f GB" % (shutil.disk_usage(str(probe)).free / 1e9))
    return 0


def cmd_runtime(args: argparse.Namespace) -> int:
    from .build import runtime

    try:
        if args.action == "path":
            for plat in ("ios", "android"):
                print("%s %s" % (plat, runtime.dist_path(plat)))
        elif args.action == "clean":
            for p in runtime.clean(all_versions=args.all):
                print("removed %s" % p)
        elif args.action == "fetch":
            if args.source:
                os.environ["PYXPO_RUNTIME_ARCHIVES"] = str(Path(args.source).resolve())
            plats = [args.platform] if args.platform else ["ios", "android"]
            if args.abi:
                known = [a["dir"].split("/", 1)[1] for a in runtime.load_manifest()["assets"].values() if a["dir"].startswith("android/")]
                if args.abi not in known:
                    raise runtime.BuildError("unknown --abi %r (available: %s)" % (args.abi, ", ".join(known)))
            for plat in plats:
                if runtime.source(plat) != "cache":
                    print("%s: using %s (%s)" % (plat, runtime.source(plat), runtime.dist_path(plat)))
                    continue
                runtime.ensure(plat, [args.abi] if args.abi else None, runtime.dist_path(plat))
                print("%s: ready in %s" % (plat, runtime.dist_path(plat)))
    except runtime.BuildError as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    return 0


def cmd_add_lib(args: argparse.Namespace) -> int:
    from . import libs

    pkg = args.package
    base = re.split(r"[<>=!~\[ ]", pkg, 1)[0].lower()
    if base in libs.HEAVY:
        print("note: %s" % libs.HEAVY[base])
        return 1
    project = Path(args.dir or ".").resolve()
    try:
        cfg = load_config(project)
    except (FileNotFoundError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    results = libs.check_package(pkg, cfg.get("targets", ["android", "ios"]))
    print(libs.format_table(pkg, results))
    missing = [t for t, (ok, _) in results.items() if not ok and t not in libs.OPTIONAL_TAGS]
    if any(not ok for t, (ok, _) in results.items() if t in libs.OPTIONAL_TAGS):
        print("note: no 32-bit ARM wheel; Android builds leave out armeabi-v7a, so phones with a 32-bit Android "
              "cannot install the app")
    requires = list(cfg.get("requires", []))
    if pkg not in requires:
        requires.append(pkg)
        set_requires(project, requires)
        print("added %s to [tool.pyxpo] requires" % pkg)
    if missing:
        print("warning: no wheel for %d tag(s); add a recipe to pyxpo-wheels or build with cibuildwheel" % len(missing))
        return 1
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    import json

    from . import app_config

    if args.schema:
        print(json.dumps(app_config.json_schema(), indent=2))
        return 0
    project = Path(args.dir or ".").resolve()
    try:
        cfg = load_config(project)
        r = native_config.resolve(cfg, project)
        for w in app_config.check_assets(r, project, cfg):
            print("warning: " + w, file=sys.stderr)
    except (FileNotFoundError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    out = r[args.platform] if args.platform else r
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


MODE_HELP = ("build mode for module build hooks such as pyxpo-dot-env (.env.<mode>); default: production with "
             "--release, else development")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pyxpo", description="Python mobile app framework")
    from . import __version__
    p.add_argument("--version", action="version", version="pyxpo %s" % __version__)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create", help="create a new project")
    c.add_argument("name")
    c.add_argument("--dir")
    c.set_defaults(fn=cmd_create)
    r = sub.add_parser("run", help="run the app")
    r.add_argument("target", nargs="?", default="desktop", choices=["desktop", "android", "ios", "web"])
    r.add_argument("--dir")
    r.add_argument("--no-reload", action="store_true", help="disable hot reload")
    r.add_argument("--port", type=int,
                   help="hot reload server port (default: dev_port or 8765, or the next free one when that is taken)")
    r.add_argument("--device", help="android: device serial or emulator (AVD) name; ios: simulator name or UDID")
    r.add_argument("--preview", action="store_true",
                   help="desktop only: quick preview in a browser window instead of building the native Mac or Windows app")
    r.add_argument("--base", help="web only: path the site is served under, such as /myapp")
    r.add_argument("--mode", help=MODE_HELP)
    r.add_argument("--no-open", action="store_true", help="web only: do not open a browser")
    r.add_argument("--no-devtools", action="store_true",
                   help="web only: hide the dev tools button (device preview, breakpoints)")
    r.set_defaults(fn=cmd_run)
    b = sub.add_parser("build", help="build a mobile package")
    b.add_argument("target", choices=["android", "ios", "desktop", "web"])
    b.add_argument("--release", action="store_true")
    b.add_argument("--mode", help=MODE_HELP)
    b.add_argument("--base", help="web only: path the site is served under, such as /myapp")
    b.add_argument("--dir")
    b.set_defaults(fn=cmd_build)
    pb = sub.add_parser("prebuild", help="generate editable android/ and ios/ native projects")
    pb.add_argument("target", nargs="?", default="all", choices=["all", "android", "ios"])
    pb.add_argument("--clean", action="store_true", help="delete the native folders first (loses your edits)")
    pb.add_argument("--yes", action="store_true", help="skip the --clean confirmation")
    pb.add_argument("--dir")
    pb.set_defaults(fn=cmd_prebuild)
    st = sub.add_parser("stage", help="refresh the Python app inside ejected native projects (run by Gradle/Xcode)")
    st.add_argument("target", choices=["android", "ios"])
    st.add_argument("--release", action="store_true")
    st.add_argument("--mode", help=MODE_HELP)
    st.add_argument("--kind", choices=["simulator", "device", "catalyst"], default="simulator", help="iOS only")
    st.add_argument("--dir")
    st.set_defaults(fn=cmd_stage)
    rt = sub.add_parser("runtime", help="manage the prebuilt CPython runtime cache")
    rt.add_argument("action", choices=["fetch", "path", "clean"])
    rt.add_argument("--platform", choices=["ios", "android"])
    rt.add_argument("--abi")
    rt.add_argument("--from", dest="source", help="directory holding the runtime .tar.gz files (offline)")
    rt.add_argument("--all", action="store_true", help="clean: remove every cached runtime version")
    rt.set_defaults(fn=cmd_runtime)
    d = sub.add_parser("doctor", help="check installed toolchains")
    d.set_defaults(fn=cmd_doctor)
    cf = sub.add_parser("config", help="print the resolved app config (validates [tool.pyxpo])")
    cf.add_argument("--platform", choices=["ios", "android"])
    cf.add_argument("--schema", action="store_true", help="print the JSON Schema for [tool.pyxpo]")
    cf.add_argument("--dir")
    cf.set_defaults(fn=cmd_config)
    a = sub.add_parser("add-lib", help="check mobile wheel availability and add a dependency")
    a.add_argument("package")
    a.add_argument("--dir")
    a.set_defaults(fn=cmd_add_lib)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "mode", None):
        from .module_hooks import MODE_ENV, check_mode
        try:
            os.environ[MODE_ENV] = check_mode(args.mode)
        except ValueError as e:
            print("error: %s" % e, file=sys.stderr)
            return 2
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
