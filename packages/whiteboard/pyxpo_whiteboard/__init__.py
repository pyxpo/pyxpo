"""A whiteboard: pen, marker, eraser, fill bucket, color picker and shapes, solid or dashed, on a plain, grid,
dot or lined page, with undo, redo, clear and PNG export.

    import pyxpo_whiteboard as WB

    @component
    def Sketch():
        board = WB.use_whiteboard(color="#222222", width=6)
        return View(
            WB.Whiteboard(board=board, style={"flex": 1}),
            WB.WhiteboardToolbar(board=board),
            style={"flex": 1},
        )

    board.undo()
    image = await board.to_image_async(trim=True)

`use_whiteboard()` holds the tool, color, width, opacity, shape fill, dashes and page pattern, and the board
state (`element_count`, `can_undo`, `can_redo`, `drawing`). The toolbar pieces (`ToolPicker`, `ShapePicker`,
`ColorPalette`, `ColorGrid`, `WidthPicker`, `OpacitySlider`, `ShapeFillToggle`, `DashToggle`, `PatternPicker`,
`HistoryButtons`) take the same board, so an app can place them in its own layout. `Whiteboard` also works on
its own with plain props and a `ref`.

The drawing is a list of elements, oldest first, in pt/dp from the view's top left:

    {"type": "stroke", "tool": "pen" | "marker" | "eraser", "color", "width", "points": [x0, y0, x1, y1, ...]}
    {"type": "shape", "shape": "line" | "arrow" | "rect" | "ellipse" | "triangle" | "star" | "diamond" |
     "hexagon" | "heart", "color", "width", "fill", "x0", "y0", "x1", "y1"}
    {"type": "fill", "x", "y", "color"}

Strokes and shapes may also have `"dash": True` (dashed line). Colors are 0xAARRGGBB ints; a shape `fill` of 0
means outline only. The page pattern is drawn on screen only, never in an exported image. A fill element floods the region under its
point when the drawing is drawn, so it stays small and follows edits made before it. iOS draws with Core
Graphics, Android with `Canvas`, the web and the desktop window with an HTML canvas.
"""
from __future__ import annotations

import base64
import math
import os
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from pyxpo import component, use_imperative_handle, use_ref, use_state
from pyxpo.module_api import call, native_view, require_linked, view_tag
from pyxpo.style import parse_color

__version__ = "0.1.0a1"

__all__ = ["Whiteboard", "WhiteboardHandle", "Board", "use_whiteboard", "Tool", "TOOLS", "DRAW_TOOLS", "SHAPES",
           "PATTERNS", "IMAGE_FORMATS", "PALETTE", "WIDTHS", "MARKER_ALPHA", "to_strokes", "transform", "bounds",
           "shape_outline", "color_grid", "WhiteboardToolbar", "ToolPicker", "ShapePicker", "ColorPalette",
           "ColorGrid", "WidthPicker", "OpacitySlider", "ShapeFillToggle", "DashToggle", "PatternPicker",
           "HistoryButtons", "ToolIcon", "ICONS", "THEME", "TOOL_LABELS", "PATTERN_LABELS"]

_View = native_view("PxWhiteboard")

DRAW_TOOLS = ("pen", "marker", "eraser", "fill", "picker")
SHAPES = ("line", "arrow", "rect", "ellipse", "triangle", "star", "diamond", "hexagon", "heart")
TOOLS = DRAW_TOOLS + SHAPES
STROKE_TOOLS = ("pen", "marker", "eraser")
PATTERNS = ("none", "grid", "dots", "lines")
PATTERN_SPACING = 24   # pt/dp between grid lines, dots and ruled lines (fixed in the renderers)
PATTERN_COLOR = 0x33808080
IMAGE_FORMATS = ("png", "jpg")
MARKER_ALPHA = 0.4   # the marker is the color at this opacity, so the ink under it shows through
PALETTE = ("#1F1A24", "#FFFFFF", "#8A8A8A", "#E5322D", "#F28C1B", "#F7C51E", "#7BC043", "#12A3A0", "#2F6FE4",
           "#8B4FD8", "#E94BA5", "#8A5A3B")
WIDTHS = (2, 4, 8, 14, 24)


class Tool:
    PEN = "pen"
    MARKER = "marker"
    ERASER = "eraser"
    FILL = "fill"
    PICKER = "picker"
    LINE = "line"
    ARROW = "arrow"
    RECT = "rect"
    ELLIPSE = "ellipse"
    TRIANGLE = "triangle"
    STAR = "star"
    DIAMOND = "diamond"
    HEXAGON = "hexagon"
    HEART = "heart"


def _choice(name: str, value: Any, allowed: tuple) -> str:
    if value not in allowed:
        raise ValueError("%s must be one of %s, got %r" % (name, ", ".join(allowed), value))
    return value


def _number(name: str, value: Any, low: float, high: float = math.inf, low_open: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("%s must be a number, got %r" % (name, value))
    if value < low or value > high or (low_open and value == low):
        raise ValueError("%s must be %s %g%s, got %r" % (name, ">" if low_open else ">=", low,
                                                         "" if high == math.inf else " and <= %g" % high, value))
    return float(value)


def _with_alpha(argb: int, k: float) -> int:
    """`argb` with its alpha times `k`."""
    a = int(round(((argb >> 24) & 255) * k))
    return (max(0, min(255, a)) << 24) | (argb & 0xFFFFFF)


def _color(name: str, value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        raise ValueError("%s must be a color, got %r" % (name, value))
    return parse_color(value)


def _element(i: int, e: Any) -> Dict[str, Any]:
    """One element in the wire format. A dict with no "type" is a stroke (the drawing-canvas format)."""
    if not isinstance(e, dict):
        raise TypeError("element %d must be a dict, got %s" % (i, type(e).__name__))
    kind = e.get("type", "stroke")
    if kind == "stroke":
        pts = e.get("points")
        if not isinstance(pts, (list, tuple)) or len(pts) % 2 or not pts:
            raise ValueError("element %d points must be a flat [x0, y0, x1, y1, ...] list" % i)
        out = {"type": "stroke", "tool": _choice("element %d tool" % i, e.get("tool", "pen"), STROKE_TOOLS),
               "color": _color("element %d color" % i, e.get("color", 0xFF000000)),
               "width": _number("element %d width" % i, e.get("width", 4), 0, low_open=True),
               "points": [_number("element %d point" % i, p, -math.inf) for p in pts]}
        if e.get("dash") and out["tool"] != "eraser":
            out["dash"] = True
        return out
    if kind == "shape":
        out: Dict[str, Any] = {"type": "shape", "shape": _choice("element %d shape" % i, e.get("shape"), SHAPES),
                               "color": _color("element %d color" % i, e.get("color", 0xFF000000)),
                               "width": _number("element %d width" % i, e.get("width", 4), 0),
                               "fill": _color("element %d fill" % i, e.get("fill"))}
        for k in ("x0", "y0", "x1", "y1"):
            out[k] = _number("element %d %s" % (i, k), e.get(k), -math.inf)
        if e.get("dash"):
            out["dash"] = True
        return out
    if kind == "fill":
        return {"type": "fill", "x": _number("element %d x" % i, e.get("x"), -math.inf),
                "y": _number("element %d y" % i, e.get("y"), -math.inf),
                "color": _color("element %d color" % i, e.get("color", 0xFF000000))}
    raise ValueError("element %d type must be stroke, shape or fill, got %r" % (i, kind))


# ---------------------------------------------------------------- geometry, shared with the native code

def shape_outline(shape: str, x0: float, y0: float, x1: float, y1: float, width: float = 0,
                  segments: int = 48) -> List[List[float]]:
    """The polylines a shape draws, as flat point lists: one closed loop, or a line plus two arrow-head lines.
    The native code builds the same paths (with a true ellipse)."""
    if shape in ("line", "arrow"):
        lines = [[x0, y0, x1, y1]]
        if shape == "arrow":
            for side in (-1, 1):
                hx, hy = _arrow_head(x0, y0, x1, y1, width, side)
                lines.append([x1, y1, hx, hy])
        return lines
    lx, ly, hx, hy = min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)
    cx, cy, rx, ry = (lx + hx) / 2, (ly + hy) / 2, (hx - lx) / 2, (hy - ly) / 2
    if shape == "rect":
        pts = [lx, ly, hx, ly, hx, hy, lx, hy]
    elif shape == "ellipse":
        pts = []
        for j in range(segments):
            a = 2 * math.pi * j / segments
            pts += [cx + rx * math.cos(a), cy + ry * math.sin(a)]
    elif shape == "triangle":
        pts = [cx, ly, hx, hy, lx, hy]
    elif shape == "star":
        pts = star_points(cx, cy, rx, ry)
    elif shape == "diamond":
        pts = [cx, ly, hx, cy, cx, hy, lx, cy]
    elif shape == "hexagon":
        pts = []
        for j in range(6):
            a = -math.pi / 2 + math.pi * j / 3
            pts += [cx + rx * math.cos(a), cy + ry * math.sin(a)]
    elif shape == "heart":
        pts = heart_points(lx, ly, hx, hy)
    else:
        raise ValueError("unknown shape %r" % shape)
    return [pts + pts[:2]]


def star_points(cx: float, cy: float, rx: float, ry: float) -> List[float]:
    """Five points, first one up; the inner corners at 0.45 of the outer radius."""
    pts: List[float] = []
    for j in range(10):
        a = -math.pi / 2 + math.pi * j / 5
        k = 1 if j % 2 == 0 else 0.45
        pts += [cx + rx * k * math.cos(a), cy + ry * k * math.sin(a)]
    return pts


def heart_points(lx: float, ly: float, hx: float, hy: float, segments: int = 48) -> List[float]:
    """The classic heart curve (x = 16 sin^3 t, y = 13 cos t - 5 cos 2t - 2 cos 3t - cos 4t) fitted to the box:
    x spans -16..16 and y -12..17, so the lobes touch the top and the point the bottom."""
    cx, w, h = (lx + hx) / 2, (hx - lx) / 2, hy - ly
    pts: List[float] = []
    for j in range(segments):
        t = 2 * math.pi * j / segments
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts += [cx + w * x / 16, ly + h * (y + 12) / 29]
    return pts


def _arrow_head(x0: float, y0: float, x1: float, y1: float, width: float, side: int) -> Tuple[float, float]:
    """The end of one arrow-head line: 28 degrees off the shaft, max(12, 3.5 x width) long, at most half the
    shaft."""
    dx, dy = x1 - x0, y1 - y0
    n = math.hypot(dx, dy) or 1.0
    size = min(max(12.0, width * 3.5), n * 0.5)
    a = math.atan2(dy, dx) + math.pi + side * math.radians(28)
    return x1 + size * math.cos(a), y1 + size * math.sin(a)


def to_strokes(elements: Sequence[Dict[str, Any]], segments: int = 48) -> List[Dict[str, Any]]:
    """The drawing as plain strokes (`{"tool", "color", "width", "points"}`), for code that reads lines only:
    shapes become their outlines, the marker draws like the pen, fill elements are left out."""
    out: List[Dict[str, Any]] = []
    for e in elements:
        kind = e.get("type", "stroke")
        if kind == "stroke":
            out.append({"tool": "eraser" if e.get("tool") == "eraser" else "pen", "color": e.get("color", 0xFF000000),
                        "width": e.get("width", 4), "points": list(e["points"])})
        elif kind == "shape":
            w = e.get("width", 4) or 1
            for pts in shape_outline(e["shape"], e["x0"], e["y0"], e["x1"], e["y1"], w, segments):
                out.append({"tool": "pen", "color": e.get("color", 0xFF000000), "width": w, "points": pts})
    return out


def transform(elements: Sequence[Dict[str, Any]], scale: float, dx: float = 0, dy: float = 0) -> List[Dict[str, Any]]:
    """Every element moved to `p * scale + (dx, dy)`, widths scaled too."""
    out = []
    for e in elements:
        kind = e.get("type", "stroke")
        if kind == "stroke":
            p = e["points"]
            pts = [v * scale + (dx if i % 2 == 0 else dy) for i, v in enumerate(p)]
            out.append(dict(e, width=float(e.get("width", 4)) * scale, points=pts))
        elif kind == "shape":
            out.append(dict(e, width=float(e.get("width", 4)) * scale, x0=e["x0"] * scale + dx,
                            y0=e["y0"] * scale + dy, x1=e["x1"] * scale + dx, y1=e["y1"] * scale + dy))
        elif kind == "fill":
            out.append(dict(e, x=e["x"] * scale + dx, y=e["y"] * scale + dy))
    return out


def bounds(elements: Sequence[Dict[str, Any]]) -> Optional[Tuple[float, float, float, float]]:
    """(x0, y0, x1, y1) of the lines and shapes, half a line width out; None when there are none. Fills and the
    eraser do not count."""
    box: List[float] = []
    for e in elements:
        kind = e.get("type", "stroke")
        if kind == "stroke" and e.get("tool") != "eraser":
            pts, r = e["points"], float(e.get("width", 4)) / 2
        elif kind == "shape":
            r = float(e.get("width", 4)) / 2
            pts = [v for line in shape_outline(e["shape"], e["x0"], e["y0"], e["x1"], e["y1"], r * 2) for v in line]
        else:
            continue
        xs, ys = pts[0::2], pts[1::2]
        b = [min(xs) - r, min(ys) - r, max(xs) + r, max(ys) + r]
        box = b if not box else [min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3])]
    return tuple(box) if box else None  # type: ignore[return-value]


# ---------------------------------------------------------------- files written for the web

def _out_dir() -> Path:
    d = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "pyxpo" / "whiteboard"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save(res: Dict[str, Any], fmt: str) -> Dict[str, Any]:
    """The web page returns the encoded image; Python writes it, so `uri` is a file like on iOS and Android."""
    data = res.pop("base64", None)
    if data is None:
        return res
    path = _out_dir() / ("%s.%s" % (uuid.uuid4().hex, fmt))
    path.write_bytes(base64.b64decode(data))
    res["uri"] = "file://" + str(path)
    return res


# ---------------------------------------------------------------- the view and its handle

class WhiteboardHandle:
    """`ref.current` of a mounted `Whiteboard`."""

    def __init__(self, view_ref: Any) -> None:
        self._view = view_ref

    def _tag(self) -> int:
        require_linked("Whiteboard", "whiteboard", package="pyxpo-whiteboard")
        tag = view_tag(self._view)
        if tag is None:
            raise RuntimeError("the Whiteboard is not mounted")
        return tag

    def undo(self) -> None:
        """Takes back the last element or `clear()`."""
        call("Whiteboard", "undo", self._tag())

    def redo(self) -> None:
        call("Whiteboard", "redo", self._tag())

    def clear(self) -> None:
        """Removes every element. `undo()` brings them back."""
        call("Whiteboard", "clear", self._tag())

    async def get_elements_async(self) -> List[Dict[str, Any]]:
        """The drawing, oldest element first (see the module docstring for the format)."""
        return list(await call("Whiteboard", "getElements", self._tag(), reply=True) or [])

    async def set_elements_async(self, elements: Sequence[Dict[str, Any]]) -> None:
        """Replaces the drawing with `elements` and empties undo and redo. Plain drawing-canvas strokes work."""
        if not isinstance(elements, (list, tuple)):
            raise TypeError("elements must be a list, got %s" % type(elements).__name__)
        clean = [_element(i, e) for i, e in enumerate(elements)]
        await call("Whiteboard", "setElements", self._tag(), clean, reply=True)

    async def to_image_async(self, format: str = "png", trim: bool = False, padding: float = 0,
                             scale: Optional[float] = None, background: bool = True,
                             quality: float = 1) -> Optional[Dict[str, Any]]:
        """Writes the drawing to an image file in the app cache: `{"uri", "width", "height", "x", "y"}`.

        `trim=True` crops to the ink plus `padding` (pt/dp); `x`, `y` are then the crop's top left in the view.
        It returns None when trimming a board with no ink. `scale` is pixels per pt/dp (default the screen's).
        `background=False` leaves the background out (transparent; a `jpg` gets white). `quality` 0-1 is for
        `jpg`."""
        fmt = _choice("format", format, IMAGE_FORMATS)
        opts: Dict[str, Any] = {"format": fmt, "trim": bool(trim), "padding": _number("padding", padding, 0),
                                "background": bool(background), "quality": _number("quality", quality, 0, 1)}
        if scale is not None:
            opts["scale"] = _number("scale", scale, 0, 8, low_open=True)
        res = await call("Whiteboard", "toImage", self._tag(), opts, reply=True)
        return _save(dict(res), fmt) if res else None

    # camelCase names
    getElementsAsync = get_elements_async
    setElementsAsync = set_elements_async
    toImageAsync = to_image_async


EMPTY = {"element_count": 0, "can_undo": False, "can_redo": False}


class Board:
    """What `use_whiteboard()` returns: the current tool settings with setters, the board state, and the
    `WhiteboardHandle` methods. A new object every render; keep `board.ref` if you need something stable."""

    def __init__(self, ref: Any, values: Dict[str, Any], set_values: Callable, state: Dict[str, Any],
                 set_state: Callable, drawing: bool, set_drawing: Callable, palette: Sequence[Any],
                 widths: Sequence[float], theme: Dict[str, Any]) -> None:
        self.ref = ref
        self._values, self._set_values = values, set_values
        self._set_state, self._set_drawing = set_state, set_drawing
        self.tool: str = values["tool"]
        self.color: Any = values["color"]
        self.width: float = values["width"]
        self.opacity: float = values["opacity"]
        self.fill_shapes: bool = values["fill_shapes"]
        self.dash: bool = values["dash"]
        self.pattern: str = values["pattern"]
        self.element_count: int = state.get("element_count", 0)
        self.can_undo: bool = bool(state.get("can_undo"))
        self.can_redo: bool = bool(state.get("can_redo"))
        self.drawing = drawing
        self.palette = tuple(palette)
        self.widths = tuple(widths)
        self.theme = theme

    @property
    def is_empty(self) -> bool:
        """No elements yet and no touch in progress: the time to show a "draw here" hint."""
        return self.element_count == 0 and not self.drawing

    def _set(self, **kw: Any) -> None:
        self._set_values(lambda v: dict(v, **kw))

    def set_tool(self, tool: str) -> None:
        """Picks a tool. The color picker remembers the tool before it and goes back to it after one pick."""
        tool = _choice("tool", tool, TOOLS)
        self._set_values(lambda v: dict(v, tool=tool, back=v["tool"] if tool == "picker" and v["tool"] != "picker"
                                        else v.get("back", "pen")))

    def set_color(self, color: Any) -> None:
        """Picks a color; from the eraser it also goes back to the pen, from the picker to the tool before it."""
        parse_color(color)
        self._set_values(lambda v: dict(v, color=color, tool="pen" if v["tool"] == "eraser" else
                                        v.get("back", "pen") if v["tool"] == "picker" else v["tool"]))

    def set_width(self, width: float) -> None:
        self._set(width=_number("width", width, 0, 500, True))

    def set_opacity(self, opacity: float) -> None:
        self._set(opacity=_number("opacity", opacity, 0, 1, True))

    def set_fill_shapes(self, on: bool) -> None:
        self._set(fill_shapes=bool(on))

    def set_dash(self, on: bool) -> None:
        """Dashed pen, marker and shape outlines from now on (the eraser is always solid)."""
        self._set(dash=bool(on))

    def set_pattern(self, pattern: str) -> None:
        """The page behind the ink: "none", "grid", "dots" or "lines". It is not part of an exported image."""
        self._set(pattern=_choice("pattern", pattern, PATTERNS))

    def _on_pick(self, e: Dict[str, Any]) -> None:
        argb = int(e.get("color", 0)) & 0xFFFFFF
        hex_color = "#%06X" % argb
        self._set_values(lambda v: dict(v, color=hex_color, tool=v.get("back", "pen")))

    def _on_change(self, s: Dict[str, Any]) -> None:
        self._set_drawing(False)
        self._set_state(s)

    def _on_draw_start(self, _: Any = None) -> None:
        self._set_drawing(True)

    def _handle(self) -> WhiteboardHandle:
        if self.ref.current is None:
            raise RuntimeError("the Whiteboard is not mounted")
        return self.ref.current

    def undo(self) -> None:
        self._handle().undo()

    def redo(self) -> None:
        self._handle().redo()

    def clear(self) -> None:
        self._handle().clear()

    async def get_elements_async(self) -> List[Dict[str, Any]]:
        return await self._handle().get_elements_async()

    async def set_elements_async(self, elements: Sequence[Dict[str, Any]]) -> None:
        await self._handle().set_elements_async(elements)

    async def to_image_async(self, **kw: Any) -> Optional[Dict[str, Any]]:
        return await self._handle().to_image_async(**kw)


def use_whiteboard(tool: str = "pen", color: Any = "#1F1A24", width: float = 4, opacity: float = 1,
                   fill_shapes: bool = False, dash: bool = False, pattern: str = "none",
                   palette: Sequence[Any] = PALETTE, widths: Sequence[float] = WIDTHS,
                   theme: Optional[Dict[str, Any]] = None) -> Board:
    """Hook: state for one `Whiteboard` and its toolbar. The arguments are the starting values; `palette` and
    `widths` are what `ColorPalette` and `WidthPicker` offer; `theme` overrides keys of `THEME` for the toolbar
    pieces."""
    from .toolbar import THEME
    ref = use_ref(None)
    values, set_values = use_state(lambda: {"tool": _choice("tool", tool, TOOLS), "color": color,
                                            "width": _number("width", width, 0, 500, True),
                                            "opacity": _number("opacity", opacity, 0, 1, True),
                                            "fill_shapes": bool(fill_shapes), "dash": bool(dash),
                                            "pattern": _choice("pattern", pattern, PATTERNS), "back": "pen"})
    state, set_state = use_state(EMPTY)
    drawing, set_drawing = use_state(False)
    return Board(ref, values, set_values, state, set_state, drawing, set_drawing, palette, widths,
                 dict(THEME, **(theme or {})))


@component
def Whiteboard(board: Optional[Board] = None, tool: str = "pen", color: Any = "#000000", width: float = 4,
               opacity: float = 1, fill_color: Any = None, background_color: Any = "#ffffff", enabled: bool = True,
               fill_tolerance: float = 32, dash: bool = False, pattern: str = "none", pattern_color: Any = None,
               on_change: Optional[Callable[[Dict[str, Any]], Any]] = None,
               on_draw_start: Optional[Callable[[Dict[str, Any]], Any]] = None,
               on_pick: Optional[Callable[[Dict[str, Any]], Any]] = None, style: Any = None, **props: Any):
    """A whiteboard sized by `style`. `ref.current` is a `WhiteboardHandle`.

    With a `board` from `use_whiteboard()` the tool settings come from it and `board.ref` is set; otherwise
    pass them as props. `width` is in pt/dp (the eraser and shape outlines use it too). `opacity` (0-1) applies
    to the pen, shapes and the fill bucket; the marker is always see-through. `fill_color` fills shapes (None:
    outline only). `fill_tolerance` (0-255) is how far a color may differ from the tapped one and still be
    filled. `dash` draws dashed lines. `pattern` ("none", "grid", "dots", "lines") lines the page in
    `pattern_color` (default a faint gray), on screen only. `on_draw_start({"tool"})` fires when a touch starts
    drawing, `on_change(state)` with `{"element_count", "can_undo", "can_redo"}` after each element, undo,
    redo, clear, `set_elements_async` and a touch that drew nothing. With the "picker" tool a tap draws nothing
    and fires `on_pick({"color"})` with the 0xAARRGGBB color under the finger (ink over the background)."""
    ref = props.pop("ref", None)
    inner = use_ref(None)
    if board is not None:
        tool, color, width, opacity = board.tool, board.color, board.width, board.opacity
        fill_color = board.color if board.fill_shapes else None
        dash, pattern = board.dash, board.pattern
        user_change, user_start, user_pick = on_change, on_draw_start, on_pick

        def on_change(s: Dict[str, Any]) -> None:
            board._on_change(s)
            if user_change is not None:
                user_change(s)

        def on_draw_start(e: Dict[str, Any]) -> None:
            board._on_draw_start(e)
            if user_start is not None:
                user_start(e)

        def on_pick(e: Dict[str, Any]) -> None:
            board._on_pick(e)
            if user_pick is not None:
                user_pick(e)

        if ref is None:
            ref = board.ref
    use_imperative_handle(ref, lambda: WhiteboardHandle(inner), [])
    _choice("tool", tool, TOOLS)
    k = _number("opacity", opacity, 0, 1, True)
    ink = _with_alpha(parse_color(color), k * (MARKER_ALPHA if tool == "marker" else 1))
    wire: Dict[str, Any] = {
        "tool": tool, "color": ink, "width": _number("width", width, 0, 500, True),
        "fill_color": _with_alpha(parse_color(fill_color), k) if fill_color is not None else 0,
        "background_color": parse_color(background_color), "enabled": bool(enabled),
        "fill_tolerance": int(round(_number("fill_tolerance", fill_tolerance, 0, 255))),
        "dash": bool(dash) and tool != "eraser", "pattern": _choice("pattern", pattern, PATTERNS),
        "pattern_color": parse_color(pattern_color) if pattern_color is not None else PATTERN_COLOR,
    }
    if on_change is not None:
        wire["on_change"] = on_change
    if on_draw_start is not None:
        wire["on_draw_start"] = on_draw_start
    if on_pick is not None:
        wire["on_pick"] = on_pick
    return _View(ref=inner, style=style, **wire, **props)


from .icons import ICONS, ToolIcon  # noqa: E402
from .toolbar import (PATTERN_LABELS, THEME, TOOL_LABELS, ColorGrid, ColorPalette, DashToggle,  # noqa: E402
                      HistoryButtons, OpacitySlider, PatternPicker, ShapeFillToggle, ShapePicker, ToolPicker,
                      WhiteboardToolbar, WidthPicker, color_grid)
