"""Gate for pyxpo-wheels: every ELF .so must be 16 KB aligned (PT_LOAD p_align >= 16384).

Usage: python wheels/check_wheel.py a.whl [b.whl ...]   (exit 1 on any unaligned lib)
"""
from __future__ import annotations

import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pyxpo.build import elfcheck  # noqa: E402


def main(wheels: list) -> int:
    bad = 0
    for w in wheels:
        with tempfile.TemporaryDirectory() as d:
            with zipfile.ZipFile(w) as z:
                z.extractall(d)
            found = elfcheck.find_unaligned([Path(d)])
        for p, a in found:
            print("%s: %s align=0x%x" % (Path(w).name, Path(p).name, a))
        print("%s: %s" % (Path(w).name, "FAIL" if found else "ok"))
        bad += bool(found)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
