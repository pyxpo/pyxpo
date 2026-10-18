# Changelog

## Unreleased

- Color picker tool (`"picker"`, `on_pick`), three more shapes (diamond, hexagon, heart), dashed lines and
  outlines (`dash`, `DashToggle`), a page pattern on screen (`pattern`: grid, dots or lined; `PatternPicker`) and
  a full color spectrum (`ColorGrid`, `color_grid`). `WhiteboardToolbar` gains `patterns` and `spectrum`.

## 0.1.0a1

- Docs: detailed README with screenshots, and fuller PyPI metadata (keywords, classifiers, project URLs).
- First release: `Whiteboard` with pen, marker, eraser, fill bucket and six shapes (line, arrow, rectangle,
  ellipse, triangle, star; outline or filled), opacity, undo, redo, clear, `get_elements_async`,
  `set_elements_async` and `to_image_async` (PNG or JPEG, optional trim to the ink). `use_whiteboard()` and the
  toolbar pieces (`WhiteboardToolbar`, `ToolPicker`, `ShapePicker`, `ColorPalette`, `WidthPicker`,
  `OpacitySlider`, `ShapeFillToggle`, `HistoryButtons`). Helpers `to_strokes`, `transform`, `bounds`. iOS,
  Android, the web and the desktop window.
