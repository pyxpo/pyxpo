"""CSS-order hex colors (#RGB, #RRGGBB, #RRGGBBAA) converted to the native orders."""
from __future__ import annotations

from typing import Tuple


def parse(c: str) -> Tuple[int, int, int, int]:
    h = c.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) == 6:
        h += "ff"
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16)


def android_argb(c: str) -> str:
    """Android resources want #AARRGGBB."""
    r, g, b, a = parse(c)
    return "#%02x%02x%02x%02x" % (a, r, g, b)


def components(c: str) -> dict:
    """iOS colorset sRGB components (0-1 floats as strings)."""
    r, g, b, a = parse(c)
    return {"red": "%.3f" % (r / 255.0), "green": "%.3f" % (g / 255.0), "blue": "%.3f" % (b / 255.0), "alpha": "%.3f" % (a / 255.0)}


def is_dark(c: str) -> bool:
    r, g, b, _ = parse(c)
    return (0.299 * r + 0.587 * g + 0.114 * b) < 128
