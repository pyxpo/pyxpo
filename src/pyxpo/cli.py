from __future__ import annotations

import argparse
import os
import re
import runpy
import secrets
import shutil
import sys
from pathlib import Path
from typing import List, Optional

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
    if args.target != "desktop":
        print("pyxpo run %s: not yet implemented (milestone 3)" % args.target, file=sys.stderr)
        return 2
    project = Path(args.dir or ".").resolve()
    try:
        load_config(project)
    except (FileNotFoundError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    os.environ["PYXPO_TARGET"] = "desktop"
    sys.path.insert(0, str(project))
    if not getattr(args, "no_reload", False):
        from .component import enable_registry
        from .dev.server import DevServer

        token = secrets.token_hex(16)
        try:
            dev = DevServer(str(project), _dev_port(args, project), token)
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


def _android(args: argparse.Namespace, run: bool) -> int:
    from .build import android as droid

    BuildError, build = droid.BuildError, droid.build
    project = Path(args.dir or ".").resolve()
    reload_on = run and not getattr(args, "no_reload", False)
    try:
        build(project, release=getattr(args, "release", False), install=run, run=run and not reload_on)
        if reload_on:
            _android_dev(droid, project, args)
    except (BuildError, FileNotFoundError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    except OSError as e:
        print("error: %s (is another `pyxpo run` using the dev port? try --port N or --no-reload)" % e, file=sys.stderr)
        return 1
    return 0


ANDROID_DEV_CONNECT_TIMEOUT = 30.0
ANDROID_DEV_RELAUNCHES = 2


def _android_dev(droid, project: Path, args: argparse.Namespace) -> None:
    """Start the dev server, reverse the port to the device, launch with dev extras, serve until Ctrl-C."""
    from .dev.server import DevServer

    cfg = load_config(project)
    token = secrets.token_hex(16)
    dev = DevServer(str(project), _dev_port(args, project), token)
    adb = droid.adb_path()
    port = str(dev.port)
    droid._run([adb, "reverse", "tcp:" + port, "tcp:" + port])
    app_id = cfg.get("bundle_id", "com.example.app")
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


def _ios(args: argparse.Namespace, run: bool) -> int:
    from .build import ios

    project = Path(args.dir or ".").resolve()
    try:
        cfg = load_config(project)
        app_id = cfg.get("bundle_id", "com.example.app")
        app = ios.build(project, release=getattr(args, "release", False))
        if not run:
            return 0
        extras = {}
        dev = None
        if not getattr(args, "no_reload", False):
            from .dev.server import DevServer

            token = secrets.token_hex(16)
            dev = DevServer(str(project), _dev_port(args, project), token)
            extras = {"PYXPO_DEV_URL": dev.url, "PYXPO_DEV_TOKEN": token}
        proc = ios.install_and_run(app, app_id, extras)
        try:
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
        print("error: %s (is another `pyxpo run` using the dev port? try --port N or --no-reload)" % e, file=sys.stderr)
        return 1
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    if args.target == "android":
        return _android(args, run=False)
    if args.target == "ios":
        return _ios(args, run=False)
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
    try:
        for t in targets:
            dest = (droid if t == "android" else ios).prebuild(project, clean=args.clean)
            print("ejected %s" % dest)
    except (ios.BuildError, FileNotFoundError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    print("edit the native files, commit them, then `pyxpo run <android|ios>` builds from them")
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
    missing = [t for t, (ok, _) in results.items() if not ok]
    requires = list(cfg.get("requires", []))
    if pkg not in requires:
        requires.append(pkg)
        set_requires(project, requires)
        print("added %s to [tool.pyxpo] requires" % pkg)
    if missing:
        print("warning: no wheel for %d tag(s); add a recipe to pyxpo-wheels or build with cibuildwheel" % len(missing))
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pyxpo", description="Python mobile app framework")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create", help="create a new project")
    c.add_argument("name")
    c.add_argument("--dir")
    c.set_defaults(fn=cmd_create)
    r = sub.add_parser("run", help="run the app")
    r.add_argument("target", nargs="?", default="desktop", choices=["desktop", "android", "ios"])
    r.add_argument("--dir")
    r.add_argument("--no-reload", action="store_true", help="disable hot reload")
    r.add_argument("--port", type=int, help="hot reload server port (default: dev_port or 8765)")
    r.set_defaults(fn=cmd_run)
    b = sub.add_parser("build", help="build a mobile package")
    b.add_argument("target", choices=["android", "ios"])
    b.add_argument("--release", action="store_true")
    b.add_argument("--dir")
    b.set_defaults(fn=cmd_build)
    pb = sub.add_parser("prebuild", help="generate editable android/ and ios/ native projects")
    pb.add_argument("target", nargs="?", default="all", choices=["all", "android", "ios"])
    pb.add_argument("--clean", action="store_true", help="delete the native folders first (loses your edits)")
    pb.add_argument("--yes", action="store_true", help="skip the --clean confirmation")
    pb.add_argument("--dir")
    pb.set_defaults(fn=cmd_prebuild)
    rt = sub.add_parser("runtime", help="manage the prebuilt CPython runtime cache")
    rt.add_argument("action", choices=["fetch", "path", "clean"])
    rt.add_argument("--platform", choices=["ios", "android"])
    rt.add_argument("--abi")
    rt.add_argument("--from", dest="source", help="directory holding the runtime .tar.gz files (offline)")
    rt.add_argument("--all", action="store_true", help="clean: remove every cached runtime version")
    rt.set_defaults(fn=cmd_runtime)
    d = sub.add_parser("doctor", help="check installed toolchains")
    d.set_defaults(fn=cmd_doctor)
    a = sub.add_parser("add-lib", help="check mobile wheel availability and add a dependency")
    a.add_argument("package")
    a.add_argument("--dir")
    a.set_defaults(fn=cmd_add_lib)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
