# pyxpo-whiteboard

A whiteboard for [pyxpo](https://github.com/pyxpo/pyxpo) apps: pen, marker, eraser, fill bucket, color picker
and shapes (line, arrow, rectangle, ellipse, triangle, star, diamond, hexagon, heart), solid or dashed lines,
opacity, a full color spectrum, a plain, grid, dotted or lined page, undo, redo, clear and export to PNG or JPEG. It
comes with a ready toolbar and with the toolbar pieces, so you can use the whole toolbar or place each control
in your own layout. iOS draws with Core Graphics, Android with `android.graphics.Canvas`, the web and the
desktop window with an HTML canvas. Every platform uses the same element format and the same geometry.

```sh
pip install pyxpo-whiteboard
```

```toml
[tool.pyxpo]
modules = ["whiteboard"]
```

```python
import pyxpo_whiteboard as WB
from pyxpo import Button, Text, View, component

@component
def Sketch():
    board = WB.use_whiteboard(color="#222222", width=4)

    async def export():
        image = await board.to_image_async(trim=True, padding=16)
        if image:
            print(image["uri"], image["width"], image["height"])

    return View(
        View(
            WB.Whiteboard(board=board, style={"flex": 1}),
            Text("Draw here", style={"position": "absolute", "top": 20, "left": 20}) if board.is_empty else None,
            style={"flex": 1},
        ),
        WB.WhiteboardToolbar(board=board),
        Button(title="Export", on_press=export),
        style={"flex": 1},
    )
```

Pass the board by keyword (`board=board`): in pyxpo, positional arguments of a component are its children.

## `use_whiteboard()`

`use_whiteboard(tool="pen", color="#1F1A24", width=4, opacity=1, fill_shapes=False, dash=False,
pattern="none", palette=PALETTE, widths=WIDTHS, theme=None)` returns a `Board`:

- Settings: `tool`, `color`, `width`, `opacity`, `fill_shapes`, `dash`, `pattern`, with `set_tool`,
  `set_color`, `set_width`, `set_opacity`, `set_fill_shapes`, `set_dash`, `set_pattern`. Picking a color while
  the eraser is on goes back to the pen. The color picker tool picks one color from the drawing and then goes
  back to the tool before it; so does a swatch picked while the picker is on.
- State: `element_count`, `can_undo`, `can_redo`, `drawing` (a touch is in progress) and `is_empty` (no
  elements and no touch: the time to show a "draw here" hint; it turns False as soon as a touch starts).
- Methods: `undo()`, `redo()`, `clear()`, `await get_elements_async()`, `await set_elements_async(elements)`,
  `await to_image_async(...)`.
- `palette` and `widths` are what `ColorPalette` and `WidthPicker` offer. `theme` overrides keys of `THEME`
  (colors and sizes of the toolbar pieces).

## Toolbar pieces

Each takes `board=` and `style`.

| Piece | |
| --- | --- |
| `WhiteboardToolbar(on_clear=None, shapes=True, opacity=True, history=True, patterns=True, spectrum=False)` | Every control in wrapping rows; narrow screens get more rows. `spectrum` adds the `ColorGrid`. |
| `ToolPicker(tools=DRAW_TOOLS)` | Pen, marker, eraser, fill bucket, color picker. |
| `ShapePicker(shapes=SHAPES)` | Line, arrow, rectangle, ellipse, triangle, star, diamond, hexagon, heart. |
| `ColorPalette(colors=None, size=None)` | Swatches that wrap; the picked one has a ring and a tick. |
| `ColorGrid(hues=12, shades=5, size=None)` | A full spectrum: light to dark rows of hues and a row of grays (`color_grid(hues, shades)` gives the colors). |
| `DashToggle()` | Solid or dashed lines and shape outlines. |
| `PatternPicker(patterns=PATTERNS)` | The page: plain, grid, dots or lined. |
| `WidthPicker(widths=None)` | Dots of each width in the current color. |
| `OpacitySlider(minimum=0.1, label=True)` | 10-100 %. |
| `ShapeFillToggle()` | Outline or filled shapes (filled with the current color). |
| `HistoryButtons(on_clear=None, clear=True)` | Undo, redo, clear. `on_clear` replaces the clear, for example to ask first. |

Buttons have `test_id`s (`wb-tool-pen`, `wb-shape-star`, `wb-color-3`, `wb-width-8`, `wb-opacity`,
`wb-fill-shapes`, `wb-dash`, `wb-pattern-grid`, `wb-grid-2-4` (row, column), `wb-undo`, `wb-redo`,
`wb-clear`) and accessibility labels and states.

## `Whiteboard` props

With `board=` the settings come from the board. Without it, pass them as props and use a `ref`.

| Prop | Default | |
| --- | --- | --- |
| `tool` | `"pen"` | `"pen"`, `"marker"`, `"eraser"`, `"fill"`, `"picker"` or a shape. |
| `color` | `"#000000"` | Any pyxpo color. The marker draws it at 40 % opacity. |
| `width` | `4` | In pt/dp, greater than 0 and at most 500. The eraser and shape outlines use it. |
| `opacity` | `1` | 0-1, for the pen, shapes and the fill bucket. |
| `fill_color` | `None` | Fills new shapes; `None` draws outlines only. |
| `fill_tolerance` | `32` | 0-255: how far a pixel may differ from the tapped one and still be filled. |
| `dash` | `False` | Dashed lines and shape outlines (never for the eraser). |
| `pattern` | `"none"` | The page under the ink: `"none"`, `"grid"`, `"dots"` or `"lines"`, every 24 pt/dp. On screen only, never in an exported image. |
| `pattern_color` | faint gray | The color of the pattern (`PATTERN_COLOR`). |
| `background_color` | `"#ffffff"` | Shown under the ink and used by `to_image_async(background=True)`. |
| `enabled` | `True` | `False` ignores touches. |
| `on_draw_start` | `None` | Called with `{"tool"}` when a touch starts. |
| `on_change` | `None` | Called with `{"element_count", "can_undo", "can_redo"}` after each element, undo, redo, clear, `set_elements_async` and a touch that drew nothing. |
| `on_pick` | `None` | With the `"picker"` tool a tap draws nothing and calls this with `{"color"}`: the 0xAARRGGBB color under the finger, ink over the background. |
| `style` | | Sizes the board, for example `{"flex": 1}`. |

## Elements

The drawing is a list, oldest first, in pt/dp from the view's top left. Colors are 0xAARRGGBB ints.

```python
{"type": "stroke", "tool": "pen" | "marker" | "eraser", "color", "width", "points": [x0, y0, x1, y1, ...]}
{"type": "shape", "shape": "line" | "arrow" | "rect" | "ellipse" | "triangle" | "star" | "diamond" | "hexagon"
 | "heart", "color", "width", "fill", "x0", "y0", "x1", "y1"}   # fill 0: outline only
# strokes (not the eraser) and shapes may add "dash": True
{"type": "fill", "x", "y", "color"}
```

A fill element floods the region under its point each time the drawing is drawn, so it stays small. A dict
with no `"type"` is a stroke, so pyxpo-drawing-canvas strokes load as they are.

- `to_strokes(elements)`: plain strokes for code that reads lines only (shapes become outlines, the marker
  becomes the pen, fills are left out).
- `transform(elements, scale, dx=0, dy=0)`: every element moved and scaled.
- `bounds(elements)`: `(x0, y0, x1, y1)` of the lines and shapes, or `None`.

## `to_image_async`

`to_image_async(format="png", trim=False, padding=0, scale=None, background=True, quality=1)` writes the
drawing to a file in the app cache and returns `{"uri", "width", "height", "x", "y"}`. `trim=True` crops to
the ink plus `padding` pt/dp and returns `None` for an empty board; `x` and `y` are the crop's top left in the
view. `scale` is pixels per pt/dp (default: the screen's). `background=False` gives a transparent PNG.
`quality` (0 to 1) is for `jpg`.

On the web and the desktop window the page encodes the image and Python writes it to
`~/.cache/pyxpo/whiteboard/` (or `$XDG_CACHE_HOME`), so `uri` is a `file://` path on every platform.
