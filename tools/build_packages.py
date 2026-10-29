"""Builds and checks the separately published native module packages (never publishes).

Each package lives in its own repo pyxpo/pyxpo-<name>. Locally they are cloned side by side in
../pyxpo-packages/pyxpo-<name> (PYXPO_PACKAGES overrides that folder).

Usage:
    python tools/build_packages.py                      # every package -> wheelhouse-packages/<name>/
    python tools/build_packages.py image-picker sharing # only these
    python tools/build_packages.py --path . --tag v0.1.0a1   # release gate in a package repo: tag must match its version
    options: --outdir DIR, --no-isolation (use the current environment's setuptools, offline)

Each package must produce a wheel and an sdist that both carry pyxpo-module.json, the iOS and Android
sources, and (wheel) the `pyxpo.modules` entry point, since autolinking reads them from the installed package.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = Path(os.environ.get("PYXPO_PACKAGES") or ROOT.parent / "pyxpo-packages")
# Packages given by --path, for a package repo checked out under any folder name.
EXTRA: Dict[str, Path] = {}


def packages() -> List[str]:
    found = [p.parent.name[len("pyxpo-"):] for p in PACKAGES.glob("pyxpo-*/pyproject.toml")]
    return sorted(set(found) | set(EXTRA))


def package_dir(name: str) -> Path:
    return EXTRA.get(name) or PACKAGES / ("pyxpo-" + name)


def name_of(path: Path) -> str:
    """The module name of the package at `path`, from its pyproject `name = "pyxpo-<name>"`."""
    m = re.search(r'^name = "pyxpo-([a-z][a-z0-9-]*)"', (path / "pyproject.toml").read_text(), re.M)
    if not m:
        raise SystemExit("%s/pyproject.toml has no `name = \"pyxpo-<name>\"`" % path)
    return m.group(1)


def import_name(name: str) -> str:
    return "pyxpo_" + name.replace("-", "_")


def version(name: str) -> str:
    init = package_dir(name) / import_name(name) / "__init__.py"
    return re.search(r'^__version__\s*=\s*"([^"]+)"', init.read_text(), re.M).group(1)


def expected_files(name: str) -> List[str]:
    """Paths (relative to the package root) every artifact must contain: Python, metadata, native sources."""
    pkg = package_dir(name) / import_name(name)
    out = []
    for f in sorted(pkg.rglob("*")):
        rel = f.relative_to(pkg)
        if f.is_file() and "__pycache__" not in rel.parts and f.name != ".DS_Store" and f.suffix != ".pyc":
            out.append("%s/%s" % (import_name(name), rel.as_posix()))
    return out


def check_wheel(whl: Path, name: str) -> List[str]:
    errors = []
    with zipfile.ZipFile(str(whl)) as z:
        names = set(z.namelist())
        for need in expected_files(name):
            if need not in names:
                errors.append("%s is missing %s" % (whl.name, need))
        eps = [n for n in names if n.endswith(".dist-info/entry_points.txt")]
        text = z.read(eps[0]).decode() if eps else ""
        if not re.search(r"\[pyxpo\.modules\]\s*\n%s\s*=\s*%s\s*(\n|$)" % (re.escape(name), import_name(name)), text):
            errors.append("%s has no `pyxpo.modules` entry point %s = %s" % (whl.name, name, import_name(name)))
        meta = json.loads(z.read("%s/pyxpo-module.json" % import_name(name))) if \
            "%s/pyxpo-module.json" % import_name(name) in names else {}
        if meta.get("name") != name:
            errors.append("%s: pyxpo-module.json name %r != package module name %r" % (whl.name, meta.get("name"), name))
        stray = [n for n in names if "__pycache__" in n or n.endswith(".pyc") or n.startswith("pyxpo/")]
        if stray:
            errors.append("%s contains unexpected files: %s" % (whl.name, ", ".join(sorted(stray)[:5])))
    return errors


def check_sdist(sdist: Path, name: str) -> List[str]:
    with tarfile.open(str(sdist)) as t:
        names = {"/".join(n.split("/")[1:]) for n in t.getnames()}
    return ["%s is missing %s" % (sdist.name, need) for need in expected_files(name) + ["pyproject.toml", "README.md", "LICENSE"]
            if need not in names]


def build(name: str, outdir: Path, isolation: bool = True) -> List[str]:
    """Builds one package into `outdir`; returns the list of problems (empty when fine)."""
    outdir.mkdir(parents=True, exist_ok=True)
    for old in list(outdir.glob("*.whl")) + list(outdir.glob("*.tar.gz")):
        old.unlink()
    cmd = [sys.executable, "-m", "build", "--outdir", str(outdir), str(package_dir(name))]
    if not isolation:
        cmd.insert(3, "--no-isolation")
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode != 0:
        return ["build of %s failed:\n%s" % (name, r.stdout[-3000:])]
    dist = "pyxpo_" + name.replace("-", "_")
    whls = sorted(outdir.glob("%s-*.whl" % dist))
    sdists = sorted(outdir.glob("%s-*.tar.gz" % dist))
    if len(whls) != 1 or len(sdists) != 1:
        return ["expected one wheel and one sdist for %s in %s" % (name, outdir)]
    errors = check_wheel(whls[0], name) + check_sdist(sdists[0], name)
    want = version(name)
    if "-%s-" % want not in whls[0].name:
        errors.append("%s does not carry version %s" % (whls[0].name, want))
    return errors


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("names", nargs="*", help="module names, for example image-picker (default: all in PYXPO_PACKAGES)")
    ap.add_argument("--path", action="append", default=[], help="a package folder outside PYXPO_PACKAGES (repeatable)")
    ap.add_argument("--outdir", default=str(ROOT / "wheelhouse-packages"))
    ap.add_argument("--tag", help="release tag v<version>; needs exactly one package and checks its version")
    ap.add_argument("--no-isolation", action="store_true")
    a = ap.parse_args(argv)
    for p in a.path:
        EXTRA[name_of(Path(p).resolve())] = Path(p).resolve()
    names = a.names + sorted(EXTRA) or packages()
    errors: List[str] = []
    if a.tag:
        m = re.match(r"^v(.+)$", a.tag)
        if not m or len(names) != 1:
            print("FAIL: --tag needs a tag v<version> and exactly one package (got %r, %s)" % (a.tag, names))
            return 1
        if names[0] in packages() and version(names[0]) != m.group(1):
            errors.append("tag %s does not match %s __version__ %s" % (a.tag, names[0], version(names[0])))
    for n in names:
        if n not in packages():
            errors.append("no package %r in %s (have: %s)" % (n, PACKAGES, ", ".join(packages())))
            continue
        out = Path(a.outdir) if a.tag else Path(a.outdir) / n
        problems = build(n, out, isolation=not a.no_isolation)
        errors += problems
        print("%-16s %s  %s" % (n, version(n), "FAILED" if problems else "ok -> %s" % out))
    for e in errors:
        print("FAIL:", e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
