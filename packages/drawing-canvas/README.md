# pyxpo-drawing-canvas

A finger and pen drawing surface for [pyxpo](https://github.com/pyxpo/pyxpo) apps written in Python, with undo, redo,
clear, a pen and an eraser, and export to PNG or JPEG. iOS draws with Core Graphics (Apple Pencil works like a finger),
Android with `android.graphics.Canvas`, and the web and the desktop window with an HTML canvas. Every platform uses the
same stroke format and the same smoothing curve, so strokes saved on one platform look the same on another.

<p align="center">
  <img src="https://raw.githubusercontent.com/pyxpo/pyxpo/main/packages/drawing-canvas/docs/images/hero.png" width="820" alt="The drawing canvas on Android and iOS, each with ink on a white page">
</p>

```python
import pyxpo_drawing_canvas as DrawingCanvas

DrawingCanvas.DrawingCanvas(ref=canvas, stroke_color="#222222", stroke_width=6, style={"flex": 1})
```

> **Note on the screenshots:** the Android picture shows five straight lines because the strokes were made with `adb`
> swipes. The iOS picture shows a curve that the demo app seeded with `set_strokes_async`. A finger draws smooth curves on both.

## Features

- **Pen and eraser** with any color and width. The eraser removes ink and leaves the page background.
- **Undo, redo and clear.** `clear()` can be undone.
- **Smooth strokes.** Quadratic curves through the midpoints of your touch points, drawn the same on every platform.
- **Save and restore.** `get_strokes_async()` returns plain data and `set_strokes_async()` puts it back.
- **Export** to PNG or JPEG, optionally trimmed to the ink, with a transparent background if you want.
- **Change events** with the stroke count and whether undo or redo is possible, for your own buttons.
- **Same code on the web and the desktop window.**
- **camelCase too:** `getStrokesAsync`, `toImageAsync`, `setStrokesAsync`.

## Contents

| If you are... | Start here |
| --- | --- |
| Adding a sketch pad | [Quick start](#quick-start) |
| Choosing pen, eraser, color and width | [Props](#drawingcanvas-props) |
| Undo, redo, clear | [Handle methods](#refcurrent-methods) |
| Saving a drawing and loading it later | [Strokes](#strokes) |
| Turning a drawing into an image | [Export](#export) |
| Need shapes, fill, a toolbar or a grid page | Use [pyxpo-whiteboard](https://pypi.org/project/pyxpo-whiteboard/) |
| Exact names | [API reference](#api-reference) · [Errors](#errors) |
| A real use | [Recipe: sign here](#recipe-a-signature-pad) |
| Stuck | [Testing](#testing) · [Troubleshooting](#troubleshooting) · [FAQ](#faq) |

## Platform support

| Target | What works |
| --- | --- |
| Android, API 24+ | Finger and stylus. Drawn with `Canvas`. |
| iOS 15+ | Finger and Apple Pencil. Drawn with Core Graphics. |
| Desktop window | Mouse and pen through pointer events. Drawn on an HTML canvas. |
| Web page | The same as the desktop window. |

Requires Python 3.9+ and `pyxpo>=0.1.0a2`.

## Install

```sh
pip install pyxpo-drawing-canvas
```

```toml
[tool.pyxpo]
modules = ["drawing-canvas"]
```

Rebuild the app. There are no permissions and no plugin options.

## Quick start

```python
from pyxpo import Button, Row, Text, View, component, use_async, use_ref, use_state
import pyxpo_drawing_canvas as DrawingCanvas


@component
def Sketch():
    canvas = use_ref(None)
    state, set_state = use_state({"stroke_count": 0, "can_undo": False, "can_redo": False})
    tool, set_tool = use_state("pen")
    exports, set_exports = use_state(0)
    saved, set_saved = use_state("")

    async def export():
        if exports > 0:
            image = await canvas.current.to_image_async(trim=True, padding=16)
            set_saved("Nothing to save" if image is None else "%d x %d px" % (image["width"], image["height"]))

    use_async(export, [exports])

    return View(
        DrawingCanvas.DrawingCanvas(ref=canvas, stroke_color="#222222", stroke_width=6, tool=tool,
                                    on_change=set_state, style={"flex": 1}),
        Text("%d strokes. %s" % (state["stroke_count"], saved)),
        Row(
            Button(title="Pen", on_press=lambda: set_tool("pen")),
            Button(title="Eraser", on_press=lambda: set_tool("eraser")),
            Button(title="Undo", disabled=not state["can_undo"], on_press=lambda: canvas.current.undo()),
            Button(title="Redo", disabled=not state["can_redo"], on_press=lambda: canvas.current.redo()),
            Button(title="Clear", on_press=lambda: canvas.current.clear()),
            Button(title="Export", on_press=lambda: set_exports(exports + 1)),
        ),
        style={"flex": 1},
    )
```

> **Tip:** `use_async(fn, deps)` awaits only a real `async def`. Do not pass `lambda: some_coroutine()`: nothing awaits it.

<p align="center">
  <img src="https://raw.githubusercontent.com/pyxpo/pyxpo/main/packages/drawing-canvas/docs/images/canvas.png" width="560" alt="Ink drawn on the canvas on Android and iOS">
</p>

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

A prop change applies to the next stroke and never recolors ink already on the page. `ref` is a `use_ref(None)`; it holds a
`DrawingCanvasHandle` once the canvas is mounted.

## `ref.current` methods

- `undo()`, `redo()`: take back or apply again the last stroke or `clear()`.
- `clear()`: removes every stroke. `undo()` brings them back.
- `await get_strokes_async()`: the visible strokes, oldest first.
- `await set_strokes_async(strokes)`: replaces the drawing and empties undo and redo.
- `await to_image_async(...)`: writes the drawing to an image file. See [Export](#export).

`undo`, `redo` and `clear` return at once and do not wait for the native side. Read the result from `on_change`.

## Strokes

Each stroke is a dict:

| Key | Meaning |
| --- | --- |
| `tool` | `"pen"` or `"eraser"`. |
| `color` | `0xAARRGGBB` int. |
| `width` | pt/dp, greater than 0. |
| `points` | Flat `[x0, y0, x1, y1, ...]` in pt/dp from the view's top left. |

```python
strokes = await canvas.current.get_strokes_async()
# [{"tool": "pen", "color": 4280361249, "width": 6.0, "points": [12.0, 40.5, 14.2, 44.0, ...]}]

await canvas.current.set_strokes_async([
    {"tool": "pen", "color": "#e5322d", "width": 8, "points": [20, 20, 120, 80, 220, 20]},
])
```

`set_strokes_async` takes any pyxpo color for `color` and defaults `tool` to `"pen"`, `width` to 4 and `color` to
opaque black. It checks every stroke before it sends anything, so a bad one raises and leaves the drawing as it was.
Points are in the canvas's own pt/dp, so a drawing saved on a phone shows at the same size and position on a canvas
of the same size, but is not rescaled for a bigger one. Scale the points yourself if you need that.

## Export

```python
image = await canvas.current.to_image_async(format="png", trim=True, padding=16, background=False)
image["uri"]      # "file:///.../cache/....png"
image["width"], image["height"]     # pixels
image["x"], image["y"]              # the crop's top left in the view, pt/dp
```

| Argument | Default | |
| --- | --- | --- |
| `format` | `"png"` | `"png"` or `"jpg"`. |
| `trim` | `False` | Crop to the ink plus `padding`. Returns `None` for an empty canvas. |
| `padding` | `0` | pt/dp around the ink when trimming. |
| `scale` | the screen's | Pixels per pt/dp, above 0 and at most 8. |
| `background` | `True` | `False` gives a transparent PNG. A JPEG gets white instead. |
| `quality` | `1` | 0 to 1, for `jpg` only. |

The file is written to the app cache. Share it with pyxpo-sharing, save it with pyxpo-media-library, or read it with pyxpo-file-system.

## Errors

| Error | When | What to do |
| --- | --- | --- |
| `ValueError` | A bad `tool`, `format`, `stroke_width`, `padding`, `scale` or `quality`. A stroke with an odd number of coordinates or none. | Fix the value. The message names it. |
| `TypeError` | `set_strokes_async` got something other than a list, or a stroke that is not a dict. | Pass a list of dicts. |
| `RuntimeError` | You used the handle before the canvas mounted. | Call it from an event, not during render. |
| `ModuleNotLinkedError` | The phone build lacks the module. | Add `"drawing-canvas"` to `modules` and rebuild. |
| `None` from `to_image_async` | `trim=True` and nothing is drawn. | Check `state["stroke_count"]` first. |

## Config

There is nothing to configure. The module has no permissions, no plugin options and no Info.plist texts.

## Web and desktop

The canvas is an HTML canvas driven by pointer events, so a mouse, a touch screen and a pen all work. The page encodes the
image and Python writes it to `~/.cache/pyxpo/drawing-canvas/` (or `$XDG_CACHE_HOME/pyxpo/drawing-canvas/`), so `uri` is a
`file://` path on every platform.

## Recipe: a signature pad

```python
from pyxpo import Button, Row, Text, View, component, use_async, use_ref, use_state
import pyxpo_drawing_canvas as DrawingCanvas


@component
def SignHere(on_signed):
    canvas = use_ref(None)
    inked, set_inked = use_state(False)
    submits, set_submits = use_state(0)

    async def submit():
        if submits > 0:
            image = await canvas.current.to_image_async(trim=True, padding=12, background=False)
            if image is not None:
                on_signed(image["uri"])

    use_async(submit, [submits])

    return View(
        Text("Sign in the box"),
        DrawingCanvas.DrawingCanvas(
            ref=canvas, stroke_color="#0b2a6f", stroke_width=3,
            on_change=lambda s: set_inked(s["stroke_count"] > 0),
            style={"height": 180, "borderWidth": 1, "borderColor": "#999999"}),
        Row(
            Button(title="Clear", on_press=lambda: canvas.current.clear()),
            Button(title="Done", disabled=not inked, on_press=lambda: set_submits(submits + 1)),
        ),
    )
```

The transparent, trimmed PNG drops cleanly onto a PDF or a form.

## Production checklist

- [ ] The canvas has a size (`style`), because a drawing surface has no content to size itself from.
- [ ] Undo and redo buttons follow `can_undo` and `can_redo` from `on_change`.
- [ ] You handle `None` from `to_image_async(trim=True)` for an empty canvas.
- [ ] Saved strokes record the canvas size, if the drawing may open on a different screen.
- [ ] Exports are copied out of the cache (or shared) if you need them later. The system may clear the cache.
- [ ] Tested with a finger on a real phone, and with Apple Pencil if you support it.

## Testing

Fake the native call, the link check and the view tag to test your own code without a device:

```python
import asyncio

import pytest

import pyxpo_drawing_canvas as dc


@pytest.fixture
def handle(monkeypatch):
    calls = []

    async def fake_call(module, method, *args, **kwargs):
        calls.append((method, args))
        if method == "getStrokes":
            return [{"tool": "pen", "color": 0xFF000000, "width": 4.0, "points": [0.0, 0.0, 5.0, 5.0]}]
        if method == "toImage":
            return {"uri": "file:///tmp/a.png", "width": 20, "height": 10, "x": 0, "y": 0}
        return None

    monkeypatch.setattr(dc, "call", fake_call)
    monkeypatch.setattr(dc, "require_linked", lambda *a, **k: None)
    monkeypatch.setattr(dc, "view_tag", lambda ref: 7)
    return dc.DrawingCanvasHandle(object()), calls


def test_strokes_round_trip(handle):
    h, calls = handle
    strokes = asyncio.run(h.get_strokes_async())
    assert strokes[0]["points"] == [0.0, 0.0, 5.0, 5.0]
    asyncio.run(h.set_strokes_async([{"points": [0, 0, 10, 10], "color": "#ff0000"}]))
    method, args = calls[-1]
    assert method == "setStrokes" and args[0] == 7
    assert args[1][0]["tool"] == "pen" and args[1][0]["width"] == 4.0


def test_bad_stroke_is_rejected_before_sending(handle):
    h, calls = handle
    with pytest.raises(ValueError):
        asyncio.run(h.set_strokes_async([{"points": [1, 2, 3]}]))
    assert calls == []


def test_export_options(handle):
    h, calls = handle
    image = asyncio.run(h.to_image_async(format="jpg", trim=True, padding=8, quality=0.8))
    assert image["width"] == 20
    opts = calls[-1][1][1]
    assert opts["format"] == "jpg" and opts["trim"] is True and opts["padding"] == 8.0
    with pytest.raises(ValueError):
        asyncio.run(h.to_image_async(format="gif"))
```

`DrawingCanvas(...)` itself only builds a native view description, so a test can call it and look at the props. A bad
`tool` or `stroke_width` raises `ValueError` while building.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Nothing shows and nothing draws | The canvas has no height. Give it `style={"flex": 1}` or a `height`. |
| Strokes do not appear | `enabled=False`, or something covers the canvas and takes the touches. |
| The eraser leaves white marks on a colored page | Set `background_color` to the page color you want to show. |
| `to_image_async` returns `None` | `trim=True` on an empty canvas. |
| The exported PNG has a white box | `background=True` is the default. Pass `background=False`. |
| `RuntimeError: the DrawingCanvas is not mounted` | You used `ref.current` before mount or after unmount. |
| `ModuleNotLinkedError` | Add `"drawing-canvas"` to `[tool.pyxpo] modules` and rebuild. |
| A restored drawing sits in the wrong place | Strokes are in pt/dp of the canvas they were drawn on. Scale the points for a different size. |

## FAQ

**Can it draw shapes, fill areas or show a grid?** Not here. [pyxpo-whiteboard](https://pypi.org/project/pyxpo-whiteboard/)
adds those, a marker, a color picker and a ready toolbar, and reads and writes the same stroke format.

**Does it support pressure from a stylus?** No. Width is fixed per stroke.

**How do I change the color of a stroke I drew?** You cannot. Read the strokes, change their `color`, and call `set_strokes_async`.

**Is the drawing kept if the view unmounts?** No. Keep the strokes yourself with `get_strokes_async()`.

**Can I draw on top of an image?** Yes. Put the canvas over an `Image` in a `View` with `background_color="transparent"`, and export with `background=False`.

## API reference

| Name | Kind | Notes |
| --- | --- | --- |
| `DrawingCanvas(...)` | component | Props above. `ref` gets a `DrawingCanvasHandle`. |
| `DrawingCanvasHandle` | class | `undo()`, `redo()`, `clear()`, `get_strokes_async()`, `set_strokes_async(strokes)`, `to_image_async(...)`. |
| `Tool` | class | `Tool.PEN`, `Tool.ERASER`. |
| `TOOLS` | tuple | `("pen", "eraser")`. |
| `IMAGE_FORMATS` | tuple | `("png", "jpg")`. |

`to_image_async(format="png", trim=False, padding=0, scale=None, background=True, quality=1)` returns
`{"uri", "width", "height", "x", "y"}` or `None`.

## License

MIT
