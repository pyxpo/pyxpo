"""PNG helpers with no dependencies: read size/alpha, write solid fixtures, resize through sips or Pillow."""
from __future__ import annotations

import shutil
import struct
import subprocess
import zlib
from pathlib import Path
from typing import Dict, Tuple

SIG = b"\x89PNG\r\n\x1a\n"


def _chunks(data: bytes):
    pos = 8
    while pos + 8 <= len(data):
        n, typ = struct.unpack(">I4s", data[pos:pos + 8])
        yield typ, data[pos + 8:pos + 8 + n]
        pos += 12 + n


def info(path) -> Dict[str, object]:
    """{width, height, has_alpha}: has_alpha is True when the image has an alpha channel with any pixel below 255."""
    data = Path(path).read_bytes()
    if data[:8] != SIG:
        raise ValueError("%s is not a PNG file" % path)
    w = h = depth = ctype = interlace = 0
    idat = b""
    trns = False
    for typ, body in _chunks(data):
        if typ == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif typ == b"IDAT":
            idat += body
        elif typ == b"tRNS":
            trns = True
    out = {"width": w, "height": h, "has_alpha": False}
    if ctype in (4, 6):
        out["has_alpha"] = _any_transparent(idat, w, h, depth, ctype, interlace)
    elif trns:
        out["has_alpha"] = True
    return out


def _any_transparent(idat: bytes, w: int, h: int, depth: int, ctype: int, interlace: int) -> bool:
    if depth != 8 or interlace:
        return True  # cannot decode cheaply: assume alpha is used
    bpp = 4 if ctype == 6 else 2
    raw = zlib.decompress(idat)
    stride = w * bpp
    prev = bytearray(stride)
    pos = 0
    for _ in range(h):
        ft, row = raw[pos], bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        for i in range(stride):
            a = row[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if ft == 1:
                row[i] = (row[i] + a) & 255
            elif ft == 2:
                row[i] = (row[i] + b) & 255
            elif ft == 3:
                row[i] = (row[i] + (a + b) // 2) & 255
            elif ft == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                row[i] = (row[i] + (a if pa <= pb and pa <= pc else (b if pb <= pc else c))) & 255
        if any(v != 255 for v in row[bpp - 1::bpp]):
            return True
        prev = row
    return False


def solid_png(w: int, h: int, rgba: Tuple[int, int, int, int] = (255, 255, 255, 255), alpha: bool = True) -> bytes:
    """A solid-color PNG (RGBA, or RGB when alpha=False)."""
    px = bytes(rgba) if alpha else bytes(rgba[:3])
    row = b"\x00" + px * w
    body = zlib.compress(row * h, 9)

    def chunk(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    return SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6 if alpha else 2, 0, 0, 0)) + chunk(b"IDAT", body) + chunk(b"IEND", b"")


def resize(src, dst, px: int) -> str:
    """Scales to px x px. Returns the backend used: 'sips', 'pillow' or 'copy' (no scaler available)."""
    src, dst = str(src), str(dst)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("sips"):
        r = subprocess.run(["sips", "-z", str(px), str(px), src, "--out", dst], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if r.returncode == 0:
            return "sips"
    try:
        from PIL import Image  # type: ignore
        Image.open(src).convert("RGBA").resize((px, px), Image.LANCZOS).save(dst)
        return "pillow"
    except ImportError:
        shutil.copyfile(src, dst)
        return "copy"
