"""Vector icons. SVG path data is parsed once into absolute move/line/cubic/close commands, which the native `Path`
view replays. Icons are 24x24, drawn as strokes (Feather style)."""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List

_TOKEN = re.compile(r"[MmLlHhVvCcSsQqAaZz]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
_ARGC = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "A": 7, "Z": 0}


def _arc(x1: float, y1: float, rx: float, ry: float, phi: float, fa: int, fs: int, x2: float, y2: float) -> List[List[float]]:
    if rx == 0 or ry == 0 or (x1 == x2 and y1 == y2):
        return [[1, x2, y2]]
    rx, ry = abs(rx), abs(ry)
    cp, sp = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cp * dx + sp * dy, -sp * dx + cp * dy
    lam = x1p ** 2 / rx ** 2 + y1p ** 2 / ry ** 2
    if lam > 1:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    num = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2
    den = rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2
    co = math.sqrt(max(0.0, num / den)) * (-1 if fa == fs else 1)
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx, cy = cp * cxp - sp * cyp + (x1 + x2) / 2, sp * cxp + cp * cyp + (y1 + y2) / 2

    def ang(ux: float, uy: float, vx: float, vy: float) -> float:
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not fs and dt > 0:
        dt -= 2 * math.pi
    elif fs and dt < 0:
        dt += 2 * math.pi
    n = max(1, int(math.ceil(abs(dt) / (math.pi / 2) - 1e-9)))
    step = dt / n
    k = 4 / 3 * math.tan(step / 4)
    out: List[List[float]] = []
    t = t1
    for _ in range(n):
        c1, s1, c2, s2 = math.cos(t), math.sin(t), math.cos(t + step), math.sin(t + step)
        p = [(c1 - k * s1), (s1 + k * c1), (c2 + k * s2), (s2 - k * c2), c2, s2]
        pts = []
        for i in range(0, 6, 2):
            ux, uy = p[i] * rx, p[i + 1] * ry
            pts += [cp * ux - sp * uy + cx, sp * ux + cp * uy + cy]
        out.append([2] + pts)
        t += step
    out[-1][-2:] = [x2, y2]
    return out


def parse_path(d: str) -> List[List[float]]:
    """SVG path data -> commands: [0,x,y] move, [1,x,y] line, [2,x1,y1,x2,y2,x,y] cubic, [3] close."""
    toks = _TOKEN.findall(d)
    out: List[List[float]] = []
    i = 0
    cmd = ""
    x = y = sx = sy = 0.0
    lcx = lcy = None  # last control point (for S)
    prev = ""
    while i < len(toks):
        if toks[i].isalpha():
            cmd = toks[i]
            i += 1
            if cmd in "Zz":
                out.append([3])
                x, y = sx, sy
                prev = "Z"
                continue
        up = cmd.upper()
        n = _ARGC[up]
        a = [float(t) for t in toks[i:i + n]]
        if len(a) < n:
            break
        i += n
        rel = cmd.islower()
        ox, oy = (x, y) if rel else (0.0, 0.0)
        if up == "M":
            x, y = a[0] + ox, a[1] + oy
            sx, sy = x, y
            out.append([0, x, y])
            cmd = "l" if rel else "L"
            prev = "M"
            continue
        if up == "L":
            x, y = a[0] + ox, a[1] + oy
            out.append([1, x, y])
        elif up == "H":
            x = a[0] + ox
            out.append([1, x, y])
        elif up == "V":
            y = a[0] + oy
            out.append([1, x, y])
        elif up == "C":
            c = [a[0] + ox, a[1] + oy, a[2] + ox, a[3] + oy, a[4] + ox, a[5] + oy]
            out.append([2] + c)
            lcx, lcy, x, y = c[2], c[3], c[4], c[5]
        elif up == "S":
            c1x, c1y = (2 * x - lcx, 2 * y - lcy) if prev == "C" and lcx is not None else (x, y)
            c = [c1x, c1y, a[0] + ox, a[1] + oy, a[2] + ox, a[3] + oy]
            out.append([2] + c)
            lcx, lcy, x, y = c[2], c[3], c[4], c[5]
        elif up == "Q":
            qx, qy, ex, ey = a[0] + ox, a[1] + oy, a[2] + ox, a[3] + oy
            out.append([2, x + 2 / 3 * (qx - x), y + 2 / 3 * (qy - y), ex + 2 / 3 * (qx - ex), ey + 2 / 3 * (qy - ey), ex, ey])
            x, y = ex, ey
        elif up == "A":
            ex, ey = a[5] + ox, a[6] + oy
            out.extend(_arc(x, y, a[0], a[1], a[2], int(a[3]), int(a[4]), ex, ey))
            x, y = ex, ey
        prev = up
    return out


PATHS: Dict[str, str] = {
    "home": "M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z M9 22V12h6v10",
    "search": "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z M21 21l-4.35-4.35",
    "user": "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2 M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
    "mail": "M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z M22 6l-10 7L2 6",
    "lock": "M5 11h14a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2z M7 11V7a5 5 0 0 1 10 0v4",
    "eye": "M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
    "eye-off": "M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94 "
               "M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19 "
               "M14.12 14.12a3 3 0 1 1-4.24-4.24 M1 1l22 22",
    "calendar": "M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z M16 2v4 M8 2v4 M3 10h18",
    "clock": "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z M12 6v6l4 2",
    "bell": "M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9 M13.73 21a2 2 0 0 1-3.46 0",
    "grid": "M3 3h7v7H3z M14 3h7v7h-7z M14 14h7v7h-7z M3 14h7v7H3z",
    "compass": "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z M16.24 7.76l-2.12 6.36-6.36 2.12 2.12-6.36 6.36-2.12z",
    "plus": "M12 5v14 M5 12h14",
    "minus": "M5 12h14",
    "close": "M18 6L6 18 M6 6l12 12",
    "check": "M20 6L9 17l-5-5",
    "chevron-down": "M6 9l6 6 6-6",
    "chevron-up": "M18 15l-6-6-6 6",
    "chevron-right": "M9 18l6-6-6-6",
    "chevron-left": "M15 18l-6-6 6-6",
    "arrow-left": "M19 12H5 M12 19l-7-7 7-7",
    "arrow-right": "M5 12h14 M12 5l7 7-7 7",
    "menu": "M3 12h18 M3 6h18 M3 18h18",
    "settings": "M4 21v-7 M4 10V3 M12 21v-9 M12 8V3 M20 21v-5 M20 12V3 M1 14h6 M9 8h6 M17 16h6",
    "info": "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z M12 16v-4 M12 8h.01",
    "success": "M22 11.08V12a10 10 0 1 1-5.93-9.14 M22 4L12 14.01l-3-3",
    "error": "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z M12 8v4 M12 16h.01",
    "heart": "M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 "
             "1.06-1.06a5.5 5.5 0 0 0 0-7.78z",
    "star": "M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z",
    "trash": "M3 6h18 M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6 M10 11v6 M14 11v6 M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2",
    "more": "M12 12h.01 M19 12h.01 M5 12h.01",
    "log-out": "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4 M16 17l5-5-5-5 M21 12H9",
    "layers": "M12 2L2 7l10 5 10-5-10-5z M2 17l10 5 10-5 M2 12l10 5 10-5",
}

_cache: Dict[str, List[List[float]]] = {}


def icon_commands(name: str) -> Any:
    if name not in PATHS:
        return None
    if name not in _cache:
        _cache[name] = parse_path(PATHS[name])
    return _cache[name]
