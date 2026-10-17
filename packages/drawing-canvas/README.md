# pyxpo-drawing-canvas

A finger and pen drawing surface for [pyxpo](https://github.com/pyxpo/pyxpo) apps, with undo, redo, clear and
export to PNG or JPEG. iOS draws with Core Graphics, Android with `android.graphics.Canvas`, the web and the
desktop window with an HTML canvas. Every platform uses the same stroke format and the same curve, so strokes
saved on one platform look the same on another.

```sh
pip install pyxpo-drawing-canvas
```

```toml
[tool.pyxpo]
modules = ["drawing-canvas"]
```

```python
import pyxpo_drawing_canvas as DrawingCanvas
from pyxpo import Button, Row, View, component, use_ref, use_state

@component
def Sketch():
    canvas = use_ref(None)
    state, set_state = use_state({"stroke_count": 0, "can_undo": False, "can_redo": False})
    tool, set_tool = use_state("pen")

    async def export():
        image = await canvas.current.to_image_async(trim=True, padding=16)
        if image:
            print(image["uri"], image["width"], image["height"])

    return View(
        DrawingCanvas.DrawingCanvas(ref=canvas, stroke_color="#222222", stroke_width=6, tool=tool,
                                    on_change=set_state, style={"flex": 1}),
        Row(
            Button(title="Pen", on_press=lambda: set_tool("pen")),
            Button(title="Eraser", on_press=lambda: set_tool("eraser")),
            Button(title="Undo", disabled=not state["can_undo"], on_press=lambda: canvas.current.undo()),
            Button(title="Redo", disabled=not state["can_redo"], on_press=lambda: canvas.current.redo()),
            Button(title="Clear", on_press=lambda: canvas.current.clear()),
            Button(title="Export", on_press=export),
        ),
        style={"flex": 1},
    )
```

## `DrawingCanvas` props

| Prop | Default | |
| --- | --- | --- |
| `stroke_color` | `"#000000"` | Any pyxpo color. Applies to the next stroke. |
| `stroke_width` | `4` | In pt/dp, greater than 0 and at most 500. The eraser uses it too. |
| `tool` | `"pen"` | `"pen"` or `"eraser"`. The eraser removes ink and leaves the background. |
| `background_color` | `"#ffffff"` | Shown under the ink and used by `to_image_async(background=True)`. |
| `enabled` | `True` | `False` ignores touches. |
| `on_change` | `None` | Called with `{"stroke_count", "can_undo", "can_redo"}` after each stroke, undo, redo, clear and `set_strokes_async`. |
| `style` | | Sizes the canvas, for example `{"flex": 1}`. |

## `ref.current` methods

- `undo()`, `redo()`: take back or apply again the last stroke or `clear()`.
- `clear()`: removes every stroke. `undo()` brings them back.
- `await get_strokes_async()`: the visible strokes, oldest first, as
  `{"tool", "color" (0xAARRGGBB), "width", "points"}`. `points` is flat `[x0, y0, x1, y1, ...]` in pt/dp from
  the view's top left.
- `await set_strokes_async(strokes)`: replaces the drawing and empties undo and redo.
- `await to_image_async(format="png", trim=False, padding=0, scale=None, background=True, quality=1)`: writes
  the drawing to a file in the app cache and returns `{"uri", "width", "height", "x", "y"}`. `trim=True` crops
  to the ink plus `padding` pt/dp and returns `None` for an empty canvas; `x` and `y` are the crop's top left in
  the view. `scale` is pixels per pt/dp (default: the screen's). `background=False` gives a transparent PNG.
  `quality` (0 to 1) is for `jpg`.

On the web and the desktop window the page encodes the image and Python writes it to
`~/.cache/pyxpo/drawing-canvas/` (or `$XDG_CACHE_HOME`), so `uri` is a `file://` path on every platform.
