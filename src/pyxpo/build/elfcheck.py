"""Check ELF shared libraries for 16 KB page-size support (Android 15+ devices, Google Play requirement)."""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

PAGE = 16384
PT_LOAD = 1
EM_AARCH64, EM_X86_64 = 183, 62


def min_load_align(path: Path) -> Optional[int]:
    """Smallest p_align over PT_LOAD segments of a 64-bit little-endian ELF, or None if not such an ELF."""
    with open(str(path), "rb") as f:
        head = f.read(64)
        if len(head) < 64 or head[:4] != b"\x7fELF" or head[4] != 2 or head[5] != 1:
            return None
        phoff, = struct.unpack_from("<Q", head, 32)
        phentsize, phnum = struct.unpack_from("<HH", head, 54)
        f.seek(phoff)
        table = f.read(phentsize * phnum)
    aligns = []
    for i in range(phnum):
        p_type, = struct.unpack_from("<I", table, i * phentsize)
        if p_type == PT_LOAD:
            aligns.append(struct.unpack_from("<Q", table, i * phentsize + 48)[0])
    return min(aligns) if aligns else None


def find_unaligned(roots: Iterable[Path]) -> List[Tuple[Path, int]]:
    """Every .so (also versioned) under roots whose LOAD segments are aligned below 16 KB."""
    bad: List[Tuple[Path, int]] = []
    for root in roots:
        for p in sorted(Path(root).rglob("*")):
            if p.is_file() and not p.is_symlink() and (p.suffix == ".so" or ".so." in p.name):
                a = min_load_align(p)
                if a is not None and a < PAGE:
                    bad.append((p, a))
    return bad
