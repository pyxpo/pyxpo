"""Prints the source footprint of each first-party native module package in ../pyxpo-packages (what `modules = [...]` adds to an app).

Usage: python tools/module_size_report.py
Unlisted modules add nothing to an app; this shows why linking them is cheap and skipping them is free.
"""
import json
import os
from pathlib import Path

ROOT = Path(os.environ.get("PYXPO_PACKAGES") or Path(__file__).resolve().parents[2] / "pyxpo-packages")


def size(paths):
    return sum(p.stat().st_size for p in paths if p.is_file())


def main() -> None:
    rows = []
    for meta in sorted(ROOT.glob("*/pyxpo_*/pyxpo-module.json")):
        d = meta.parent
        m = json.loads(meta.read_text())
        rows.append((m["name"], size(d.glob("*.py")), size((d / "ios").rglob("*.swift")),
                     size((d / "android").rglob("*.kt")), ",".join(m.get("android", {}).get("dependencies", [])) or "-"))
    print("%-16s %8s %8s %8s  %s" % ("module", "python", "swift", "kotlin", "android deps"))
    for r in rows:
        print("%-16s %8d %8d %8d  %s" % r)
    print("%-16s %8d %8d %8d" % ("total", sum(r[1] for r in rows), sum(r[2] for r in rows), sum(r[3] for r in rows)))


if __name__ == "__main__":
    main()
