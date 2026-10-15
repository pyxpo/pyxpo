"""Builds and checks the separately published native module packages in packages/ (never publishes).

Usage:
    python tools/build_packages.py                      # every package -> wheelhouse-packages/<name>/
    python tools/build_packages.py image-picker sharing # only these
    python tools/build_packages.py --tag pkg/image-picker/v0.1.0   # release gate: one package, tag must match its version
    options: --outdir DIR, --no-isolation (use the current environment's setuptools, offline)

Each package must produce a wheel and an sdist that both carry pyxpo-module.json, the iOS and Android
sources, and (wheel) the `pyxpo.modules` entry point, since autolinking reads them from the installed package.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"


def packages() -> List[str]:
    return sorted(p.parent.name for p in PACKAGES.glob("*/pyproject.toml"))


def import_name(name: str) -> str:
    return "pyxpo_" + name.replace("-", "_")


def version(name: str) -> str:
    init = PACKAGES / name / import_name(name) / "__init__.py"
    return re.search(r'^__version__\s*=\s*"([^"]+)"', init.read_text(), re.M).group(1)


def expected_files(name: str) -> List[str]:
    """Paths (relative to the package root) every artifact must contain: Python, metadata, native sources."""
    pkg = PACKAGES / name / import_name(name)
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
    cmd = [sys.executable, "-m", "build", "--outdir", str(outdir), str(PACKAGES / name)]
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
    ap.add_argument("names", nargs="*", help="package folders under packages/ (default: all)")
    ap.add_argument("--outdir", default=str(ROOT / "wheelhouse-packages"))
    ap.add_argument("--tag", help="release tag pkg/<name>/v<version>; builds only that package and checks the version")
    ap.add_argument("--no-isolation", action="store_true")
    a = ap.parse_args(argv)
    names = a.names or packages()
    errors: List[str] = []
    if a.tag:
        m = re.match(r"^pkg/([a-z][a-z0-9-]*)/v(.+)$", a.tag)
        if not m:
            print("FAIL: tag %r is not pkg/<name>/v<version>" % a.tag)
            return 1
        names = [m.group(1)]
        if m.group(1) in packages() and version(m.group(1)) != m.group(2):
            errors.append("tag %s does not match %s __version__ %s" % (a.tag, m.group(1), version(m.group(1))))
    for n in names:
        if n not in packages():
            errors.append("no package %r in packages/ (have: %s)" % (n, ", ".join(packages())))
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
