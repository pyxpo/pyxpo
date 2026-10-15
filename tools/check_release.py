"""Release gate: tag matches __version__, wheel is small and complete, every runtime asset URL resolves.

Core only: the native module packages in packages/ are released separately (tools/build_packages.py --tag).
"""
from __future__ import annotations

import json
import re
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

MAX_WHEEL = 5 * 1024 * 1024


def main(tag: str, wheelhouse: str) -> int:
    root = Path(__file__).resolve().parents[1]
    version = re.search(r'__version__\s*=\s*"([^"]+)"', (root / "src/pyxpo/__init__.py").read_text()).group(1)
    errors = []
    if tag.lstrip("v") != version:
        errors.append("tag %s does not match __version__ %s" % (tag, version))
    wheels = sorted(Path(wheelhouse).glob("*.whl"))
    if len(wheels) != 1:
        errors.append("expected exactly one wheel in %s, found %d" % (wheelhouse, len(wheels)))
    else:
        w = wheels[0]
        if w.stat().st_size > MAX_WHEEL:
            errors.append("wheel is %d bytes, over the %d limit" % (w.stat().st_size, MAX_WHEEL))
        names = zipfile.ZipFile(str(w)).namelist()
        for need in ("pyxpo/build/runtime_manifest.json", "pyxpo/_native/common/pyxpo_layout.c",
                     "pyxpo/templates/ios/user/project.yml"):
            if need not in names:
                errors.append("wheel is missing %s" % need)
        modules = [n for n in names if n.startswith(("pyxpo/modules/", "pyxpo_"))]
        if modules:
            errors.append("core wheel must not contain native module packages: %s" % ", ".join(modules[:5]))
    for sd in sorted(Path(wheelhouse).glob("*.tar.gz")):
        with tarfile.open(str(sd)) as t:
            leaked = [n for n in t.getnames() if "/packages/" in n or "/pyxpo/modules/" in n]
        if leaked:
            errors.append("%s must not contain packages/: %s" % (sd.name, ", ".join(leaked[:5])))
    m = json.loads((root / "src/pyxpo/build/runtime_manifest.json").read_text())
    if not m["assets"]:
        errors.append("runtime manifest has no assets")
    for name, a in m["assets"].items():
        url = m["base_url"] + a["file"]
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=30) as r:
                if r.status != 200:
                    errors.append("%s -> HTTP %s" % (url, r.status))
        except Exception as e:  # noqa: BLE001
            errors.append("%s unreachable: %s" % (url, e))
    for e in errors:
        print("FAIL:", e)
    print("release check %s" % ("FAILED" if errors else "ok"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
