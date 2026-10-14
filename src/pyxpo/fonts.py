"""Custom fonts. Put .ttf/.otf files in `app/fonts/`, `assets/fonts/` or `fonts/` and use the file stem as `font_family`.

Resolution is lazy: the first lookup scans `fonts/` under every sys.path entry. Native receives an
absolute `font_file` next to `font_family` and loads it. Generic names (sans-serif, serif, monospace,
system) need no file.
"""
from __future__ import annotations

import os
import sys
from typing import Dict, Optional

_EXTS = (".ttf", ".otf")
_files: Dict[str, str] = {}
_scanned: set = set()


def register_font(family: str, path: str) -> None:
    if not os.path.isfile(path):
        raise FileNotFoundError("font file not found: %s" % path)
    _files[family] = os.path.abspath(path)


def register_font_dir(directory: str) -> None:
    if not os.path.isdir(directory):
        return
    for name in sorted(os.listdir(directory)):
        stem, ext = os.path.splitext(name)
        if ext.lower() in _EXTS:
            _files.setdefault(stem, os.path.abspath(os.path.join(directory, name)))


def resolve(family: str) -> Optional[str]:
    for p in sys.path:
        for sub in ("fonts", os.path.join("app", "fonts"), os.path.join("assets", "fonts")):
            d = os.path.join(p or ".", sub)
            if d not in _scanned:
                _scanned.add(d)
                register_font_dir(d)
    return _files.get(family)
