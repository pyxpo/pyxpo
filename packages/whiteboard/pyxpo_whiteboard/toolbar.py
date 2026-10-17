"""Toolbar pieces for a `use_whiteboard()` board. Each one takes `board=` and an optional `style`, so an app
can use `WhiteboardToolbar` as is or place the pieces in its own layout. Colors and sizes come from
`board.theme` (see `THEME`)."""
from __future__ import annotations

from typing import Any, Callable, Optional, Sequence

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

TOOL_LABELS = {"pen": "Pen", "marker": "Marker", "eraser": "Eraser", "fill": "Fill bucket", "line": "Line",
               "arrow": "Arrow", "rect": "Rectangle", "ellipse": "Ellipse", "triangle": "Triangle", "star": "Star"}
DRAW_TOOLS = ("pen", "marker", "eraser", "fill")
SHAPES = ("line", "arrow", "rect", "ellipse", "triangle", "star")


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
    """Pen, marker, eraser and fill bucket buttons (or `tools`)."""
    return _tools(board, tools, style, "wb-tool")


@component
def ShapePicker(board: Any, shapes: Sequence[str] = SHAPES, style: Any = None):
    """Line, arrow, rectangle, ellipse, triangle and star buttons (or `shapes`)."""
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
                      opacity: bool = True, history: bool = True, style: Any = None):
    """Every control in wrapping rows: tools and shapes, colors, widths with the shape fill, opacity, history.
    It fits any width; narrow screens get more rows."""
    t = board.theme
    gap = t["gap"]
    row = {"flexDirection": "row", "flexWrap": "wrap", "alignItems": "center", "gap": gap}
    shape = board.tool in SHAPES
    return View(
        View(ToolPicker(board=board), ShapePicker(board=board) if shapes else None,
             HistoryButtons(board=board, on_clear=on_clear) if history else None, style=row),
        ColorPalette(board=board),
        View(WidthPicker(board=board), ShapeFillToggle(board=board) if shapes and shape else None, style=row),
        OpacitySlider(board=board) if opacity and board.tool != "eraser" else None,
        style=[{"gap": gap + 2}, style],
    )
