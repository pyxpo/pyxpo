"""A finger and pen drawing surface with undo, redo, clear and PNG export.

    import pyxpo_drawing_canvas as DrawingCanvas
    from pyxpo import use_ref

    canvas = use_ref(None)

    DrawingCanvas.DrawingCanvas(ref=canvas, stroke_color="#222", stroke_width=6, style={"flex": 1},
                                on_change=lambda s: print(s["stroke_count"], s["can_undo"], s["can_redo"]))

    canvas.current.undo()
    image = await canvas.current.to_image_async(trim=True)
    image["uri"], image["width"], image["height"], image["x"], image["y"]

Strokes are smoothed quadratic curves. The eraser removes ink and leaves the background. iOS draws with Core
Graphics (Apple Pencil works like a finger), Android with `Canvas`, the web and the desktop window with an HTML
canvas and pointer events.
"""
from __future__ import annotations

import base64
import math
import os
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from pyxpo import component, use_imperative_handle, use_ref
from pyxpo.module_api import call, native_view, require_linked, view_tag
from pyxpo.style import parse_color

__version__ = "0.1.0a1"

__all__ = ["DrawingCanvas", "DrawingCanvasHandle", "Tool", "TOOLS", "IMAGE_FORMATS"]

_View = native_view("PxDrawingCanvas")

TOOLS = ("pen", "eraser")
IMAGE_FORMATS = ("png", "jpg")


class Tool:
    PEN = "pen"
    ERASER = "eraser"


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


def _stroke(i: int, s: Any) -> Dict[str, Any]:
    if not isinstance(s, dict):
        raise TypeError("stroke %d must be a dict, got %s" % (i, type(s).__name__))
    pts = s.get("points")
    if not isinstance(pts, (list, tuple)) or len(pts) % 2 or not pts:
        raise ValueError("stroke %d points must be a flat [x0, y0, x1, y1, ...] list" % i)
    return {
        "tool": _choice("stroke %d tool" % i, s.get("tool", "pen"), TOOLS),
        "color": parse_color(s.get("color", 0xFF000000)),
        "width": _number("stroke %d width" % i, s.get("width", 4), 0, low_open=True),
        "points": [_number("stroke %d point" % i, p, -math.inf) for p in pts],
    }


def _out_dir() -> Path:
    d = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "pyxpo" / "drawing-canvas"
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


class DrawingCanvasHandle:
    """`ref.current` of a mounted `DrawingCanvas`."""

    def __init__(self, view_ref: Any) -> None:
        self._view = view_ref

    def _tag(self) -> int:
        require_linked("DrawingCanvas", "drawing-canvas", package="pyxpo-drawing-canvas")
        tag = view_tag(self._view)
        if tag is None:
            raise RuntimeError("the DrawingCanvas is not mounted")
        return tag

    def undo(self) -> None:
        """Takes back the last stroke or `clear()`."""
        call("DrawingCanvas", "undo", self._tag())

    def redo(self) -> None:
        call("DrawingCanvas", "redo", self._tag())

    def clear(self) -> None:
        """Removes every stroke. `undo()` brings them back."""
        call("DrawingCanvas", "clear", self._tag())

    async def get_strokes_async(self) -> List[Dict[str, Any]]:
        """The visible strokes, oldest first: `{"tool", "color" (0xAARRGGBB), "width", "points"}`. `points` is
        flat `[x0, y0, x1, y1, ...]` in pt/dp from the view's top left."""
        return list(await call("DrawingCanvas", "getStrokes", self._tag(), reply=True) or [])

    async def set_strokes_async(self, strokes: List[Dict[str, Any]]) -> None:
        """Replaces the drawing with `strokes` (as `get_strokes_async` returns them) and empties undo and redo."""
        if not isinstance(strokes, (list, tuple)):
            raise TypeError("strokes must be a list, got %s" % type(strokes).__name__)
        clean = [_stroke(i, s) for i, s in enumerate(strokes)]
        await call("DrawingCanvas", "setStrokes", self._tag(), clean, reply=True)

    async def to_image_async(self, format: str = "png", trim: bool = False, padding: float = 0,
                             scale: Optional[float] = None, background: bool = True,
                             quality: float = 1) -> Optional[Dict[str, Any]]:
        """Writes the drawing to an image file in the app cache: `{"uri", "width", "height", "x", "y"}`.

        `trim=True` crops to the ink plus `padding` (pt/dp); `x`, `y` are then the crop's top left in the view.
        It returns None when trimming a canvas with no ink. `scale` is pixels per pt/dp (default the screen's).
        `background=False` leaves the background out (transparent; a `jpg` gets white). `quality` 0-1 is for
        `jpg`."""
        fmt = _choice("format", format, IMAGE_FORMATS)
        opts: Dict[str, Any] = {"format": fmt, "trim": bool(trim), "padding": _number("padding", padding, 0),
                                "background": bool(background), "quality": _number("quality", quality, 0, 1)}
        if scale is not None:
            opts["scale"] = _number("scale", scale, 0, 8, low_open=True)
        res = await call("DrawingCanvas", "toImage", self._tag(), opts, reply=True)
        return _save(dict(res), fmt) if res else None

    # camelCase names
    getStrokesAsync = get_strokes_async
    setStrokesAsync = set_strokes_async
    toImageAsync = to_image_async


@component
def DrawingCanvas(stroke_color: Any = "#000000", stroke_width: float = 4, tool: str = "pen",
                  background_color: Any = "#ffffff", enabled: bool = True,
                  on_change: Optional[Callable[[Dict[str, Any]], Any]] = None, style: Any = None, **props: Any):
    """A drawing surface sized by `style`. `ref.current` is a `DrawingCanvasHandle`.

    `stroke_width` is in pt/dp; the eraser uses it too. A prop change applies to the next stroke.
    `enabled=False` ignores touches. `on_change(state)` gets `{"stroke_count", "can_undo", "can_redo"}` after
    each stroke, undo, redo, clear and `set_strokes_async`."""
    ref = props.pop("ref", None)
    inner = use_ref(None)
    use_imperative_handle(ref, lambda: DrawingCanvasHandle(inner), [])
    wire: Dict[str, Any] = {
        "stroke_color": parse_color(stroke_color), "stroke_width": _number("stroke_width", stroke_width, 0, 500, True),
        "tool": _choice("tool", tool, TOOLS), "background_color": parse_color(background_color),
        "enabled": bool(enabled),
    }
    if on_change is not None:
        wire["on_change"] = on_change
    return _View(ref=inner, style=style, **wire, **props)
