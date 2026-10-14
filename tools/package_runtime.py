"""Package a prebuilt CPython tree into a reproducible .tar.gz for a runtime release, and print its manifest entry.

Usage (from the repo root):
  python tools/package_runtime.py ios dist/ios out/
  python tools/package_runtime.py android-arm64-v8a dist/android/arm64-v8a out/

iOS stdlib is byte-compiled here (unchecked-hash .pyc, so mtimes do not matter) with a 3.13 host interpreter
given by --host-python, because the app bundle is read-only and a pip-installed pyxpo has no 3.13 on the host.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

DROP_TOP = {"testbed", "README.md", "android.py", "android-env.sh"}
SKIP_DIRS = {"__pycache__"}
MTIME = 1_700_000_000


def dir_for(name: str) -> str:
    if name == "ios":
        return "ios"
    if name.startswith("android-"):
        return "android/" + name[len("android-"):]
    raise SystemExit("asset name must be 'ios' or 'android-<abi>'")


def compile_stdlib(root: Path, host_python: str) -> None:
    for lib in root.glob("Python.xcframework/*/lib/python3.13"):
        # stdlib test data has deliberately broken files, so compileall exits 1; judge by the result instead
        subprocess.run([host_python, "-m", "compileall", "-q", "-j0", "--invalidation-mode", "unchecked-hash",
                        "-x", r"/(test|tests|idlelib|tkinter|turtledemo|lib2to3|ensurepip)/", str(lib)],
                       check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not list((lib / "__pycache__").glob("os.*.pyc")):
            raise SystemExit("compiling %s produced no .pyc; is --host-python a 3.13 interpreter?" % lib)


def add_tree(tar: tarfile.TarFile, root: Path, keep_pycache: bool) -> None:
    entries = []
    for dp, dns, fns in os.walk(str(root)):
        rel_dir = Path(dp).relative_to(root)
        if rel_dir == Path("."):
            dns[:] = [d for d in dns if d not in DROP_TOP]
            fns[:] = [f for f in fns if f not in DROP_TOP]
        if not keep_pycache:
            dns[:] = [d for d in dns if d not in SKIP_DIRS]
        dns.sort()
        entries.append(rel_dir)
        entries.extend(rel_dir / f for f in sorted(fns))
        entries.extend(rel_dir / d for d in dns if (Path(dp) / d).is_symlink())
    for rel in sorted(set(entries)):
        if str(rel) == ".":
            continue
        full = root / rel
        ti = tar.gettarinfo(str(full), arcname=str(rel))
        ti.uid = ti.gid = 0
        ti.uname = ti.gname = ""
        ti.mtime = MTIME
        ti.mode = (0o755 if ti.isdir() or ti.mode & 0o111 else 0o644)
        if ti.isreg():
            with open(str(full), "rb") as f:
                tar.addfile(ti, f)
        else:
            tar.addfile(ti)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("src", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--host-python", help="3.13 interpreter used to precompile the iOS stdlib")
    ap.add_argument("--runtime", default=None, help="runtime version, used in the file name")
    a = ap.parse_args()
    rt = a.runtime or json.loads((Path(__file__).resolve().parents[1] / "src/pyxpo/build/runtime_manifest.json").read_text())["runtime"]
    if a.name == "ios" and a.host_python:
        compile_stdlib(a.src, a.host_python)
    a.out.mkdir(parents=True, exist_ok=True)
    fname = "pyxpo-runtime-%s-%s.tar.gz" % (rt, a.name)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=9) as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar:
            add_tree(tar, a.src, keep_pycache=a.name == "ios")
    data = buf.getvalue()
    (a.out / fname).write_bytes(data)
    print(json.dumps({a.name: {"file": fname, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
                               "dir": dir_for(a.name)}}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
