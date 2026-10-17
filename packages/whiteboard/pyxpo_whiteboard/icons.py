"""Line icons for the whiteboard tools, as 24x24 SVG path data drawn with `pyxpo.vector_icons.Path`."""
from __future__ import annotations

from typing import Any

from pyxpo.vector_icons import Path

ICONS = {
    "pen": "M4 20l4-1L19 8l-3-3L5 16z M14 7l3 3",
    "marker": "M9 15l-3 3v3h3l3-3 M9 15l8-8 3 3-8 8z M15 9l3 3 M4 21h4",
    "eraser": "M8 20h12 M5.5 15.5l9-9a2 2 0 0 1 2.8 0l2.2 2.2a2 2 0 0 1 0 2.8L12 19H8.8z M10 11l5 5",
    "fill": "M11 4l8 8-7 7a2 2 0 0 1-2.8 0L4 13.8a2 2 0 0 1 0-2.8z M4.5 12h14 M8 3l3 3"
            " M20 16c1 1.6 1.5 2.6 1.5 3.3a1.5 1.5 0 0 1-3 0c0-.7.5-1.7 1.5-3.3z",
    "line": "M5 19L19 5",
    "arrow": "M5 19L19 5 M10 5h9v9",
    "rect": "M4 6h16v12H4z",
    "ellipse": "M3 12a9 6.5 0 1 0 18 0a9 6.5 0 1 0-18 0z",
    "triangle": "M12 4l9 16H3z",
    "star": "M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z",
    "shapes": "M3 10.5l4.5-7.5 4.5 7.5z M13 13h8v8h-8z M3 17a4 4 0 1 0 8 0a4 4 0 1 0-8 0z",
    "fill-shape": "M4 6h16v12H4z",
    "undo": "M9 14L4 9l5-5 M4 9h10a6 6 0 0 1 0 12h-3",
    "redo": "M15 14l5-5-5-5 M20 9H10a6 6 0 0 0 0 12h3",
    "trash": "M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3",
    "check": "M5 12.5l4.5 4.5L19 7",
}


def ToolIcon(name: str, size: float = 24, color: Any = "#1F1A24", weight: float = 2.2, fill: Any = None,
             style: Any = None):
    """The `name` icon in `color`; `fill` paints the inside of closed shapes too."""
    return Path(d=ICONS[name], stroke=color, fill=fill, stroke_width=weight,
                style=[{"width": size, "height": size}, style])
