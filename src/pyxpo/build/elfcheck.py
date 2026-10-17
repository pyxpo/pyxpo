"""Check ELF shared libraries for 16 KB page-size support (Android 15+ devices, Google Play requirement)."""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

PAGE = 16384
PT_LOAD = 1
PT_GNU_RELRO = 0x6474E552
EM_AARCH64, EM_X86_64 = 183, 62


def min_load_align(path: Path) -> Optional[int]:
    """Alignment the Android linker sees in a 64-bit little-endian ELF: the smallest PT_LOAD p_align, lowered
    the way bionic does (linker_phdr_16kib_compat.cpp) when the RELRO segment is a prefix of a bigger RW LOAD
    segment and ends on a smaller boundary. binutils-linked libraries (Chaquopy's libgfortran) can have 64 KB
    p_align and still a RELRO end aligned to 4 KB only. None if not such an ELF."""
    with open(str(path), "rb") as f:
        head = f.read(64)
        if len(head) < 64 or head[:4] != b"\x7fELF" or head[4] != 2 or head[5] != 1:
            return None
        phoff, = struct.unpack_from("<Q", head, 32)
        phentsize, phnum = struct.unpack_from("<HH", head, 54)
        f.seek(phoff)
        table = f.read(phentsize * phnum)
    loads, relros = [], []
    for i in range(phnum):
        p_type, _, _, vaddr, _, _, memsz, align = struct.unpack_from("<IIQQQQQQ", table, i * phentsize)
        if p_type == PT_LOAD:
            loads.append((vaddr, memsz, align))
        elif p_type == PT_GNU_RELRO:
            relros.append((vaddr, memsz))
    if not loads:
        return None
    best = min(a for _, _, a in loads)
    if len(relros) == 1:
        r_vaddr, r_memsz = relros[0]
        for vaddr, memsz, _ in loads:
            if vaddr == r_vaddr:
                end = r_vaddr + r_memsz
                low = end & -end
                if memsz > r_memsz and low >= 4096:
                    best = min(best, low)
                break
    return best


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
