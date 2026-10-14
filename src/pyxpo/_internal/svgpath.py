"""SVG path data -> absolute move/line/cubic/close commands, which the native `Path` view replays."""
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
