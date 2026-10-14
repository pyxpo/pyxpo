"""Scroll helpers: ScrollRef (imperative scroll_to) and FlatList (windowed list built on ScrollView)."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from . import modules
from .component import component
from .element import ScrollView, View
from .env import use_window_dimensions
from .hooks import use_callback, use_memo, use_ref, use_state
from .style import flatten


class ScrollRef:
    """Pass as `ref=` to a ScrollView or FlatList (`list_ref=`) to scroll it from code."""

    def __init__(self) -> None:
        self.id: Optional[int] = None

    def _bind(self, id: int) -> None:
        self.id = id

    def _unbind(self, id: int) -> None:
        if self.id == id:
            self.id = None

    def scroll_to(self, x: float = 0, y: float = 0, animated: bool = True) -> None:
        if self.id is not None:
            modules.call("Scroll", "to", self.id, float(x), float(y), bool(animated))

    def scroll_to_end(self, animated: bool = True) -> None:
        if self.id is not None:
            modules.call("Scroll", "to_end", self.id, bool(animated))


def use_scroll_ref() -> ScrollRef:
    return use_memo(ScrollRef, [])


def _key_of(item: Any, index: int, key_extractor: Optional[Callable[[Any, int], Any]]) -> Any:
    if key_extractor is not None:
        return key_extractor(item, index)
    if isinstance(item, dict):
        for k in ("key", "id"):
            if k in item:
                return item[k]
    return index


def _node(x: Any) -> Any:
    return x() if callable(x) and not hasattr(x, "type") else x


def window_range(offset: float, viewport: float, stride: float, rows: int, window_size: float) -> tuple:
    """Rows [first, last) to render for a scroll offset. `window_size` is in viewport lengths (RN default 21)."""
    pad = viewport * max(0.0, window_size - 1) / 2
    first = max(0, int((offset - pad) // stride))
    last = min(rows, int(-(-(offset + viewport + pad) // stride)))
    return first, max(first, last)


@component
def FlatList(data: Optional[List[Any]] = None, render_item: Optional[Callable[[Any, int], Any]] = None,
             key_extractor: Optional[Callable[[Any, int], Any]] = None, item_size: Optional[float] = None,
             separator_size: float = 0, item_separator: Any = None, horizontal: bool = False, num_columns: int = 1,
             list_header_component: Any = None, list_footer_component: Any = None, list_empty_component: Any = None,
             on_end_reached: Optional[Callable[[], Any]] = None, on_end_reached_threshold: float = 0.5,
             initial_num_to_render: int = 10, batch_size: int = 10, window_size: float = 5,
             extra_data: Any = None, style: Any = None, content_container_style: Any = None,
             on_scroll: Any = None, list_ref: Optional[ScrollRef] = None, **props: Any):
    """Scrolling list of `render_item(item, index)` rows.

    With a fixed `item_size` (row height, or width when `horizontal`) the list is windowed: only rows near the
    viewport exist, the rest is spacer. Without it rows are added in `batch_size` steps as the user nears the end.
    `separator_size` is the extent of `item_separator` (needed to place the window).
    """
    data = list(data or [])
    n = len(data)
    cols = 1 if horizontal else max(1, int(num_columns))
    rows = -(-n // cols)
    win = use_window_dimensions()
    vp0 = win["width"] if horizontal else win["height"]
    st, set_st = use_state({"offset": 0.0, "viewport": float(vp0), "content": 0.0, "head": 0.0})
    shown, set_shown = use_state(int(initial_num_to_render))
    fired = use_ref(None)
    prop = "width" if horizontal else "height"
    stride = (item_size + separator_size) if item_size is not None else 0

    ae = on_scroll if getattr(on_scroll, "_is_animated_event", False) else None

    def span(offset: float, viewport: float, head: float) -> tuple:
        return window_range(offset - head, viewport, stride, rows, window_size)

    def on_scroll_evt(e: Dict[str, Any]) -> None:
        off = e["x"] if horizontal else e["y"]
        vp = e["width"] if horizontal else e["height"]
        ct = e["content_width"] if horizontal else e["content_height"]
        # re-render only when the rendered window changes, not on every scroll tick
        moved = (span(off, vp, st["head"]) != span(st["offset"], st["viewport"], st["head"])
                 if item_size is not None else False)
        if moved or vp != st["viewport"] or ct != st["content"]:
            set_st({**st, "offset": float(off), "viewport": float(vp), "content": float(ct)})
        if on_end_reached is not None and ct > 0:
            key = (n, ct)
            if off + vp >= ct - vp * on_end_reached_threshold and fired.current != key:
                fired.current = key
                on_end_reached()
        if item_size is None and off + vp >= ct - vp * 1.5 and shown < rows:
            set_shown(shown + batch_size)
        if ae is not None:
            if not ae.native:
                ae(e)
            elif ae.listener is not None:
                ae.listener(e)
        elif on_scroll is not None:
            on_scroll(e)

    def on_head_layout(e: Dict[str, Any]) -> None:
        h = float(e[prop])
        if h != st["head"]:
            set_st({**st, "head": h})

    out: List[Any] = []
    if list_header_component is not None:
        out.append(View(_node(list_header_component), on_layout=on_head_layout, key="__head"))

    if n == 0:
        if list_empty_component is not None:
            out.append(View(_node(list_empty_component), key="__empty"))
    else:
        if item_size is not None:
            first, last = span(st["offset"], st["viewport"], st["head"])
        else:
            first, last = 0, min(rows, max(shown, 1))
        if first > 0:
            out.append(View(style={prop: first * stride}, key="__top"))
        for r in range(first, last):
            fixed = {prop: item_size} if item_size is not None else {}
            if cols == 1:
                out.append(View(render_item(data[r], r), style=fixed, key=_key_of(data[r], r, key_extractor)))
            else:
                cells = []
                for c in range(cols):
                    i = r * cols + c
                    cells.append(View(render_item(data[i], i), style={"flex": 1}, key=_key_of(data[i], i, key_extractor))
                                 if i < n else View(style={"flex": 1}, key="pad%d" % c))
                out.append(View(*cells, style={"flex_direction": "row", **fixed}, key="r%d" % r))
            if item_separator is not None and r < rows - 1:
                out.append(View(_node(item_separator), key="s%d" % r))
        if item_size is not None and last < rows:
            out.append(View(style={prop: (rows - last) * stride}, key="__bottom"))

    if list_footer_component is not None:
        out.append(View(_node(list_footer_component), key="__foot"))

    handler: Any = on_scroll_evt
    if ae is not None and ae.native:
        from .animated.api import AnimatedEvent
        handler = AnimatedEvent(ae.map, listener=on_scroll_evt, use_native_driver=True)
    return ScrollView(*out, horizontal=horizontal, style=style, content_container_style=content_container_style,
                      on_scroll=handler, ref=list_ref, **props)
