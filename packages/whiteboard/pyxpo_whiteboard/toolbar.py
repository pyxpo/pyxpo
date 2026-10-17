"""Toolbar pieces for a `use_whiteboard()` board. Each one takes `board=` and an optional `style`, so an app
can use `WhiteboardToolbar` as is or place the pieces in its own layout. Colors and sizes come from
`board.theme` (see `THEME`)."""
from __future__ import annotations

import colorsys
from typing import Any, Callable, List, Optional, Sequence

from pyxpo import Pressable, Slider, Text, View, component
from pyxpo.style import parse_color

from .icons import ToolIcon

THEME = {
    "ink": "#1F1A24",          # icons and labels
    "muted": "#8A8494",        # disabled icons, secondary labels
    "surface": "#FFFFFF",      # selected button face
    "soft": "#F2EEE8",         # the pill behind a group of buttons
    "border": "#1F1A24",       # selected button and swatch ring
    "accent": "#FFC42E",       # the selected tool's face
    "on_accent": "#1F1A24",
    "track": "#D9D2C7",        # the slider track
    "button": 44,              # button size, pt/dp
    "swatch": 32,              # color swatch size
    "gap": 8,
}

TOOL_LABELS = {"pen": "Pen", "marker": "Marker", "eraser": "Eraser", "fill": "Fill bucket",
               "picker": "Color picker", "line": "Line", "arrow": "Arrow", "rect": "Rectangle", "ellipse": "Ellipse",
               "triangle": "Triangle", "star": "Star", "diamond": "Diamond", "hexagon": "Hexagon", "heart": "Heart"}
PATTERN_LABELS = {"none": "Plain page", "grid": "Grid", "dots": "Dots", "lines": "Lined page"}
PATTERN_ICONS = {"none": "page", "grid": "grid", "dots": "dots", "lines": "lines"}
DRAW_TOOLS = ("pen", "marker", "eraser", "fill", "picker")
SHAPES = ("line", "arrow", "rect", "ellipse", "triangle", "star", "diamond", "hexagon", "heart")
PATTERNS = ("none", "grid", "dots", "lines")


def _button(child: Any, on_press: Optional[Callable], theme: dict, selected: bool = False, label: str = "",
            disabled: bool = False, size: Optional[float] = None, test_id: Optional[str] = None, key: Any = None):
    s = size or theme["button"]
    return Pressable(
        child, key=key, on_press=on_press, disabled=disabled, hit_slop=2, accessibility_label=label,
        accessibility_role="button", accessibility_state={"selected": selected, "disabled": disabled},
        test_id=test_id,
        style={"width": s, "height": s, "borderRadius": s / 2, "alignItems": "center", "justifyContent": "center",
               "borderWidth": 2, "borderColor": theme["border"] if selected else "transparent",
               "backgroundColor": theme["accent"] if selected else "transparent"},
    )


def _group(children: list, theme: dict, style: Any = None, wrap: bool = True):
    return View(*children, style=[{"flexDirection": "row", "flexWrap": "wrap" if wrap else "nowrap",
                                   "alignItems": "center", "backgroundColor": theme["soft"], "borderRadius": 999,
                                   "padding": 3, "gap": 2, "alignSelf": "flex-start", "maxWidth": "100%"}, style])


def _tools(board: Any, tools: Sequence[str], style: Any, prefix: str):
    t = board.theme
    icon = t["button"] * 0.5
    return _group([_button(ToolIcon(name, icon, t["on_accent"] if board.tool == name else t["ink"]),
                           (lambda n=name: board.set_tool(n)), t, board.tool == name, TOOL_LABELS[name],
                           test_id="%s-%s" % (prefix, name), key=name) for name in tools], t, style)


@component
def ToolPicker(board: Any, tools: Sequence[str] = DRAW_TOOLS, style: Any = None):
    """Pen, marker, eraser, fill bucket and color picker buttons (or `tools`)."""
    return _tools(board, tools, style, "wb-tool")


@component
def ShapePicker(board: Any, shapes: Sequence[str] = SHAPES, style: Any = None):
    """Line, arrow, rectangle, ellipse, triangle, star, diamond, hexagon and heart buttons (or `shapes`)."""
    return _tools(board, shapes, style, "wb-shape")


def _luma(color: Any) -> float:
    c = parse_color(color)
    return (0.299 * ((c >> 16) & 255) + 0.587 * ((c >> 8) & 255) + 0.114 * (c & 255)) / 255


@component
def ColorPalette(board: Any, colors: Optional[Sequence[Any]] = None, size: Optional[float] = None,
                 style: Any = None):
    """Color swatches; they wrap to more rows when the space is narrow. The picked one has a ring and a tick."""
    t = board.theme
    s = size or t["swatch"]
    picked = parse_color(board.color)
    out = []
    for i, c in enumerate(colors or board.palette):
        on = parse_color(c) == picked
        tick = ToolIcon("check", s * 0.55, "#FFFFFF" if _luma(c) < 0.6 else "#1F1A24", 2.6) if on else None
        out.append(Pressable(
            View(tick, style={"width": s, "height": s, "borderRadius": s / 2, "backgroundColor": c,
                              "alignItems": "center", "justifyContent": "center",
                              "borderWidth": 1, "borderColor": "rgba(0,0,0,0.18)"}),
            key=i, on_press=lambda c=c: board.set_color(c), hit_slop=2, accessibility_role="button",
            accessibility_label="Color %d" % (i + 1), accessibility_state={"selected": on},
            test_id="wb-color-%d" % i,
            style={"padding": 2, "borderRadius": s, "borderWidth": 2,
                   "borderColor": t["border"] if on else "transparent"},
        ))
    return View(*out, style=[{"flexDirection": "row", "flexWrap": "wrap", "gap": t["gap"] / 2,
                              "alignItems": "center"}, style])


def color_grid(hues: int = 12, shades: int = 5) -> List[List[str]]:
    """Rows of "#RRGGBB" colors: `shades` rows from light to dark, each with `hues` colors around the color
    wheel, and a last row of grays from white to black."""
    if hues < 1 or shades < 1:
        raise ValueError("hues and shades must be at least 1")

    def hex_of(r: float, g: float, b: float) -> str:
        return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))

    rows = []
    for j in range(shades):
        light = 0.82 - 0.6 * j / max(1, shades - 1) if shades > 1 else 0.5
        rows.append([hex_of(*colorsys.hls_to_rgb(i / hues, light, 0.85)) for i in range(hues)])
    rows.append([hex_of(*(1 - i / max(1, hues - 1),) * 3) for i in range(hues)])
    return rows


@component
def ColorGrid(board: Any, hues: int = 12, shades: int = 5, size: Optional[float] = None, style: Any = None):
    """A full spectrum to pick from: rows of light to dark hues and a row of grays (see `color_grid`).
    Square swatches; the picked one has a ring."""
    t = board.theme
    s = size or round(t["swatch"] * 0.75)
    picked = parse_color(board.color) & 0xFFFFFF
    rows = []
    for j, row in enumerate(color_grid(hues, shades)):
        cells = []
        for i, c in enumerate(row):
            on = parse_color(c) & 0xFFFFFF == picked
            cells.append(Pressable(
                key=i, on_press=lambda c=c: board.set_color(c), hit_slop=1, accessibility_role="button",
                accessibility_label="Color %s" % c, accessibility_state={"selected": on},
                test_id="wb-grid-%d-%d" % (j, i),
                style={"width": s, "height": s, "borderRadius": 4, "backgroundColor": c,
                       "borderWidth": 2 if on else 1,
                       "borderColor": t["border"] if on else "rgba(0,0,0,0.12)"},
            ))
        rows.append(View(*cells, key=j, style={"flexDirection": "row", "gap": 2}))
    return View(*rows, style=[{"gap": 2, "alignSelf": "flex-start"}, style])


@component
def WidthPicker(board: Any, widths: Optional[Sequence[float]] = None, style: Any = None):
    """Line width buttons, each a dot of that width in the current color."""
    t = board.theme
    ws = list(widths or board.widths)
    top = max(ws)
    room = t["button"] - 14
    out = []
    for w in ws:
        d = max(4.0, room * (w / top) ** 0.7)
        on = abs(board.width - w) < 1e-6
        out.append(_button(View(style={"width": d, "height": d, "borderRadius": d / 2,
                                       "backgroundColor": t["on_accent"] if on and board.tool == "eraser"
                                       else board.color}),
                           lambda w=w: board.set_width(w), t, on, "Width %g" % w, test_id="wb-width-%g" % w,
                           key=w))
    return _group(out, t, style)


@component
def OpacitySlider(board: Any, minimum: float = 0.1, label: bool = True, style: Any = None):
    """Opacity 10-100 % for the pen, shapes and fill bucket."""
    t = board.theme
    return View(
        Text("Opacity", style={"color": t["muted"], "fontSize": 13, "fontWeight": "600"}) if label else None,
        Slider(value=board.opacity, minimum_value=minimum, maximum_value=1, step=0.05,
               on_value_change=board.set_opacity, minimum_track_tint_color=t["ink"],
               maximum_track_tint_color=t["track"], thumb_tint_color=t["ink"], test_id="wb-opacity",
               accessibility_label="Opacity", style={"flex": 1, "minWidth": 80}),
        Text("%d%%" % round(board.opacity * 100),
             style={"color": t["ink"], "fontSize": 13, "fontWeight": "700", "width": 40, "textAlign": "right"}),
        style=[{"flexDirection": "row", "alignItems": "center", "gap": t["gap"]}, style],
    )


@component
def ShapeFillToggle(board: Any, style: Any = None):
    """Outline or filled shapes."""
    t = board.theme
    on = board.fill_shapes
    ink = t["on_accent"] if on else t["ink"]
    return _button(ToolIcon("fill-shape", t["button"] * 0.5, ink, fill=board.color if on else None),
                   lambda: board.set_fill_shapes(not on), t, on, "Fill shapes", test_id="wb-fill-shapes")


@component
def DashToggle(board: Any, style: Any = None):
    """Solid or dashed lines for the pen, marker and shape outlines."""
    t = board.theme
    on = board.dash
    return _button(ToolIcon("dash", t["button"] * 0.5, t["on_accent"] if on else t["ink"], 2.6),
                   lambda: board.set_dash(not on), t, on, "Dashed lines", test_id="wb-dash")


@component
def PatternPicker(board: Any, patterns: Sequence[str] = PATTERNS, style: Any = None):
    """Plain, grid, dotted or lined page behind the drawing."""
    t = board.theme
    icon = t["button"] * 0.5
    return _group([_button(ToolIcon(PATTERN_ICONS[p], icon, t["on_accent"] if board.pattern == p else t["ink"]),
                           (lambda p=p: board.set_pattern(p)), t, board.pattern == p, PATTERN_LABELS[p],
                           test_id="wb-pattern-%s" % p, key=p) for p in patterns], t, style)


@component
def HistoryButtons(board: Any, on_clear: Optional[Callable[[], Any]] = None, clear: bool = True,
                   style: Any = None):
    """Undo, redo and clear. `on_clear` replaces the clear (to ask first); without it the board clears."""
    t = board.theme
    icon = t["button"] * 0.5

    def tint(ok: bool) -> str:
        return t["ink"] if ok else t["muted"]

    empty = board.element_count == 0
    return _group([
        _button(ToolIcon("undo", icon, tint(board.can_undo)), board.undo, t, label="Undo",
                disabled=not board.can_undo, test_id="wb-undo", key="undo"),
        _button(ToolIcon("redo", icon, tint(board.can_redo)), board.redo, t, label="Redo",
                disabled=not board.can_redo, test_id="wb-redo", key="redo"),
        _button(ToolIcon("trash", icon, tint(not empty)), on_clear or board.clear, t, label="Clear",
                disabled=empty, test_id="wb-clear", key="clear") if clear else None,
    ], t, style, wrap=False)


@component
def WhiteboardToolbar(board: Any, on_clear: Optional[Callable[[], Any]] = None, shapes: bool = True,
                      opacity: bool = True, history: bool = True, patterns: bool = True, spectrum: bool = False,
                      style: Any = None):
    """Every control in wrapping rows: tools, shapes and history; colors (and the full `ColorGrid` with
    `spectrum`); widths with dashes and the shape fill; opacity; the page pattern. It fits any width; narrow
    screens get more rows."""
    t = board.theme
    gap = t["gap"]
    row = {"flexDirection": "row", "flexWrap": "wrap", "alignItems": "center", "gap": gap}
    shape = board.tool in SHAPES
    return View(
        View(ToolPicker(board=board), ShapePicker(board=board) if shapes else None,
             HistoryButtons(board=board, on_clear=on_clear) if history else None, style=row),
        ColorPalette(board=board),
        ColorGrid(board=board) if spectrum else None,
        View(WidthPicker(board=board), DashToggle(board=board) if board.tool != "eraser" else None,
             ShapeFillToggle(board=board) if shapes and shape else None, style=row),
        OpacitySlider(board=board) if opacity and board.tool != "eraser" else None,
        PatternPicker(board=board) if patterns else None,
        style=[{"gap": gap + 2}, style],
    )
