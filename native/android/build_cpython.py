#!/usr/bin/env python3
"""Cross-build CPython for Android using CPython's own in-tree Android/android.py (PEP 738).

Usage: python native/android/build_cpython.py [--abi arm64-v8a --abi x86_64] [--version 3.13.7]
Output: dist/android/<abi>/{include,lib,jniLibs...} extracted from the package tarball + manifest.json (sha256).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import shutil
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".cache"
HOSTS = {"arm64-v8a": "aarch64-linux-android", "x86_64": "x86_64-linux-android"}


def _git_index(src: Path) -> None:
    # android.py `package` lists Android/ files with `git ls-files`; release tarballs have no repo.
    if not (src / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=str(src), check=True)
    subprocess.run(["git", "add", "Android"], cwd=str(src), check=True)


def fetch_source(version: str) -> Path:
    src = CACHE / ("Python-%s" % version)
    if src.is_dir():
        _git_index(src)
        return src
    CACHE.mkdir(exist_ok=True)
    tgz = CACHE / ("Python-%s.tgz" % version)
    if not tgz.exists():
        urllib.request.urlretrieve("https://www.python.org/ftp/python/%s/Python-%s.tgz" % (version, version), tgz)
    with tarfile.open(tgz) as t:
        t.extractall(CACHE)
    _git_index(src)
    return src


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def build(abi: str, src: Path, version: str) -> None:
    host = HOSTS[abi]
    env = dict(os.environ)
    env.setdefault("ANDROID_HOME", str(Path.home() / "Library/Android/sdk"))
    host_py = next((shutil.which(n) for n in ("python3.13", "python3.12", "python3.11", "python3.10") if shutil.which(n)), None)
    if host_py is None:
        raise SystemExit("android.py needs Python >= 3.10 on PATH")
    py = [host_py, str(src / "Android" / "android.py")]
    subprocess.run(py + ["build", host], check=True, cwd=src, env=env)
    subprocess.run(py + ["package", host], check=True, cwd=src, env=env)
    tars = sorted((src / "cross-build" / host / "dist").glob("*.tar.gz"))
    if not tars:
        raise SystemExit("no package tarball found for %s" % host)
    out = ROOT / "dist" / "android" / abi
    out.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tars[-1]) as t:
        t.extractall(out)
    files = {str(p.relative_to(out)): sha256(p) for p in sorted(out.rglob("*")) if p.is_file() and p.name != "manifest.json"}
    (out / "manifest.json").write_text(json.dumps({"python": version, "abi": abi, "files": files}, indent=1))
    print("built %s: %d files -> %s" % (abi, len(files), out))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--abi", action="append", choices=sorted(HOSTS))
    ap.add_argument("--version", default="3.13.7")
    args = ap.parse_args()
    src = fetch_source(args.version)
    for abi in args.abi or ["arm64-v8a", "x86_64"]:
        build(abi, src, args.version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
