"""Android: load the shared libraries that wheels ship next to their extension modules.

Android wheels keep the libraries their extensions link against outside the APK's native lib dir: Chaquopy's
numpy needs site/chaquopy/lib/libopenblas.so, auditwheel-style wheels use site/<dist>.libs. The Android linker
does not search those dirs, so `import numpy` fails with: dlopen failed: library "libopenblas.so" not found.
The linker reuses a library that is already loaded under the same soname, so before an extension module loads
we load (dependencies first) each library it needs that a wheel ships."""
from __future__ import annotations

import ctypes
import os
import struct
import sys
from importlib.machinery import ExtensionFileLoader
from typing import Callable, Dict, Iterable, List, Optional, Set

PT_LOAD, PT_DYNAMIC = 1, 2
DT_NULL, DT_NEEDED, DT_STRTAB = 0, 1, 5

_installed = False


def needed(path: str) -> List[str]:
    """DT_NEEDED sonames of an ELF shared library, in order. [] if the file is not a readable ELF."""
    try:
        with open(path, "rb") as f:
            return _needed(f)
    except (OSError, struct.error, ValueError):
        return []


def _needed(f) -> List[str]:
    head = f.read(64)
    if len(head) < 52 or head[:4] != b"\x7fELF" or head[4] not in (1, 2) or head[5] not in (1, 2):
        return []
    is64 = head[4] == 2
    end = "<" if head[5] == 1 else ">"
    if is64:
        phoff, = struct.unpack_from(end + "Q", head, 32)
        phentsize, phnum = struct.unpack_from(end + "HH", head, 54)
        ph_fmt, dyn_fmt = end + "IIQQQQ", end + "qQ"  # p_type, p_flags, p_offset, p_vaddr, p_paddr, p_filesz
    else:
        phoff, = struct.unpack_from(end + "I", head, 28)
        phentsize, phnum = struct.unpack_from(end + "HH", head, 42)
        ph_fmt, dyn_fmt = end + "IIIIII", end + "iI"  # p_type, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz
    f.seek(phoff)
    table = f.read(phentsize * phnum)
    loads, dynamic = [], None
    for i in range(phnum):
        v = struct.unpack_from(ph_fmt, table, i * phentsize)
        p_type, offset, vaddr, filesz = (v[0], v[2], v[3], v[5]) if is64 else (v[0], v[1], v[2], v[4])
        if p_type == PT_LOAD:
            loads.append((vaddr, offset, filesz))
        elif p_type == PT_DYNAMIC:
            dynamic = (offset, filesz)
    if dynamic is None:
        return []
    f.seek(dynamic[0])
    raw = f.read(dynamic[1])
    size = struct.calcsize(dyn_fmt)
    strtab, names = None, []
    for i in range(len(raw) // size):
        tag, val = struct.unpack_from(dyn_fmt, raw, i * size)
        if tag == DT_NULL:
            break
        if tag == DT_NEEDED:
            names.append(val)
        elif tag == DT_STRTAB:
            strtab = val
    if strtab is None:
        return []
    base = next((off + strtab - va for va, off, sz in loads if va <= strtab < va + sz), None)
    if base is None:
        return []
    out = []
    for n in names:
        f.seek(base + n)
        s = f.read(256)
        out.append(s[:s.index(b"\0")].decode("utf-8", "replace") if b"\0" in s else s.decode("utf-8", "replace"))
    return out


def lib_dirs(path: Iterable[str]) -> List[str]:
    """Dirs where wheels on `path` keep shared libraries: <entry>/chaquopy/lib and <entry>/*.libs."""
    dirs = []
    for entry in path:
        if not entry or not os.path.isdir(entry):
            continue
        cands = [os.path.join(entry, "chaquopy", "lib")]
        cands += sorted(os.path.join(entry, n) for n in os.listdir(entry) if n.endswith(".libs"))
        dirs += [d for d in cands if os.path.isdir(d)]
    return dirs


def _dlopen(name: str, path: str) -> None:
    try:  # one the APK already ships or loaded (libc++_shared.so): never load a second copy
        ctypes.CDLL(name, mode=ctypes.RTLD_GLOBAL)
    except OSError:
        ctypes.CDLL(path, mode=ctypes.RTLD_GLOBAL)


class Preloader:
    """Loads the wheel-shipped libraries an ELF file needs, dependencies first, each one once."""

    def __init__(self, dirs: Iterable[str], load: Optional[Callable[[str, str], None]] = None) -> None:
        self.dirs = list(dirs)
        self.load = load
        self.loaded: Set[str] = set()
        self._index: Optional[Dict[str, str]] = None

    def index(self) -> Dict[str, str]:
        if self._index is None:  # built on first use: wheel dirs do not change while the app runs
            self._index = {}
            for d in self.dirs:
                for n in sorted(os.listdir(d)):
                    self._index.setdefault(n, os.path.join(d, n))
        return self._index

    def before(self, path: str) -> None:
        self._walk(path, set())

    def _walk(self, path: str, seen: Set[str]) -> None:
        for name in needed(path):
            lib = self.index().get(name)
            if lib is None or name in self.loaded or name in seen:
                continue
            seen.add(name)
            self._walk(lib, seen)
            try:
                (self.load or _dlopen)(name, lib)
            except OSError as e:  # the extension's own import error then names the library
                sys.stderr.write("pyxpo: could not load %s: %s\n" % (lib, e))
                continue
            self.loaded.add(name)


def install(path: Optional[Iterable[str]] = None) -> Optional[Preloader]:
    """Load wheel-shipped libraries before each extension module from now on. Returns None if no wheel ships
    any (nothing to do) or if already installed."""
    global _installed
    if _installed:
        return None
    dirs = lib_dirs(sys.path if path is None else path)
    if not dirs:
        return None
    pre = Preloader(dirs)
    original = ExtensionFileLoader.create_module

    def create_module(self, spec):
        pre.before(self.path)
        return original(self, spec)

    ExtensionFileLoader.create_module = create_module
    _installed = True
    return pre
