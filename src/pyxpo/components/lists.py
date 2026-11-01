"""FlatList, SectionList and VirtualizedList on top of ScrollView.

Lists are windowed like RN's VirtualizedList: rows far outside the viewport unmount. `getItemLayout` (RN) or
`item_size` gives exact row sizes; without them each row is measured on layout and unmeasured rows are estimated
from the average.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from ..component import component
from ..hooks import use_imperative_handle, use_ref, use_state, use_window_dimensions
from .refresh_control import RefreshControl
from .scroll_view import ScrollView
from .view import View

_SEPARATORS = {"highlight": lambda: None, "unhighlight": lambda: None, "updateProps": lambda *a: None}


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


def measured_range(offset: float, viewport: float, sizes: Dict[int, float], rows: int, window_size: float,
                   min_rows: int) -> tuple:
    """Rows [first, last) plus the spacer lengths above and below them, for rows of measured `sizes` (row -> length).
    Unmeasured rows count as the average measured length. Before anything is measured, the first `min_rows`."""
    if not sizes:
        return 0, min(rows, max(min_rows, 1)), 0.0, 0.0
    avg = sum(sizes.values()) / len(sizes)
    pad = viewport * max(0.0, window_size - 1) / 2
    lo, hi = offset - pad, offset + viewport + pad
    y, first, top, last = 0.0, -1, 0.0, rows
    for r in range(rows):
        if first < 0 and y + sizes.get(r, avg) > lo:
            first, top = r, y
        if y >= hi:
            last = r
            break
        y += sizes.get(r, avg)
    if first < 0:  # scrolled past the estimated end: keep the last rows
        first = max(0, rows - max(min_rows, 1))
        top = sum(sizes.get(r, avg) for r in range(first))
        y = top + sum(sizes.get(r, avg) for r in range(first, rows))
    if first == 0:
        last = max(last, min(rows, max(min_rows, 1)))
        y = sum(sizes.get(r, avg) for r in range(last))
    total = sum(sizes.values()) + avg * (rows - len(sizes))
    return first, max(first, last), top, max(0.0, total - y)


class FlatListHandle:
    """`ref.current` of a FlatList."""

    def __init__(self, scroll: Any, geometry: Callable[[], Dict[str, Any]]) -> None:
        self._scroll, self._geo = scroll, geometry

    def _sv(self) -> Any:
        return self._scroll.current

    def scrollToOffset(self, params: Optional[Dict[str, Any]] = None, **kw: Any) -> None:
        o = {**(params or {}), **kw}
        sv = self._sv()
        if sv is not None:
            horizontal = self._geo()["horizontal"]
            pos = float(o.get("offset", 0))
            sv.scrollTo(x=pos if horizontal else 0, y=0 if horizontal else pos, animated=o.get("animated", True))

    def scrollToIndex(self, params: Optional[Dict[str, Any]] = None, **kw: Any) -> None:
        o = {**(params or {}), **kw}
        g = self._geo()
        row = int(o.get("index", 0)) // g["cols"]
        pos = g["head"] + row * g["stride"] - float(o.get("viewPosition", o.get("view_position", 0))) * (
            g["viewport"] - g["stride"]) + float(o.get("viewOffset", o.get("view_offset", 0)))
        self.scrollToOffset({"offset": max(0.0, pos), "animated": o.get("animated", True)})

    def scrollToEnd(self, params: Optional[Dict[str, Any]] = None, **kw: Any) -> None:
        sv = self._sv()
        if sv is not None:
            sv.scrollToEnd({**(params or {}), **kw})

    def flashScrollIndicators(self) -> None:
        return None

    scroll_to_offset, scroll_to_index, scroll_to_end = scrollToOffset, scrollToIndex, scrollToEnd


@component
def FlatList(data: Optional[List[Any]] = None, render_item: Optional[Callable] = None,
             key_extractor: Optional[Callable[[Any, int], Any]] = None, get_item_layout: Optional[Callable] = None,
             item_size: Optional[float] = None, horizontal: bool = False, num_columns: int = 1,
             item_separator_component: Any = None, list_header_component: Any = None,
             list_footer_component: Any = None, list_empty_component: Any = None,
             column_wrapper_style: Any = None, on_end_reached: Optional[Callable] = None,
             on_end_reached_threshold: float = 0.5, initial_num_to_render: int = 10,
             max_to_render_per_batch: int = 10, window_size: float = 5, extra_data: Any = None,
             refreshing: Optional[bool] = None, on_refresh: Optional[Callable] = None, style: Any = None,
             content_container_style: Any = None, on_scroll: Any = None, **props: Any):
    """RN FlatList. `renderItem({"item", "index", "separators"})`; `ref.current` has scrollToIndex / scrollToOffset /
    scrollToEnd. `getItemLayout(data, index) -> {"length", "offset", "index"}` (or `item_size`) enables windowing."""
    data = list(data or [])
    ref = props.pop("ref", None)
    n = len(data)
    cols = 1 if horizontal else max(1, int(num_columns))
    rows = -(-n // cols)
    win = use_window_dimensions()
    vp0 = win["width"] if horizontal else win["height"]
    st, set_st = use_state({"offset": 0.0, "viewport": float(vp0), "content": 0.0, "head": 0.0})
    shown, set_shown = use_state(int(initial_num_to_render))  # rows to render until any row is measured
    _ver, set_ver = use_state(0)  # bumped when a measured row size moves the window
    sizes_ref = use_ref(None)
    if sizes_ref.current is None:
        sizes_ref.current = {"sizes": {}, "handlers": {}, "first": 0, "last": 0, "n": n}
    meas = sizes_ref.current
    if meas["n"] != n:  # rows past the end are gone; keep sizes of the rows that are left
        meas["sizes"] = {r: v for r, v in meas["sizes"].items() if r * cols < n}
        meas["n"] = n
    fired = use_ref(None)
    sref = use_ref(None)
    prop = "width" if horizontal else "height"

    length, stride = item_size, item_size
    if get_item_layout is not None and n:
        first = get_item_layout(data, 0)
        length = stride = float(first["length"])
        if n > cols:
            stride = float(get_item_layout(data, cols)["offset"]) - float(first["offset"])
    windowed = length is not None
    stride = stride or 0

    geo = {"horizontal": horizontal, "cols": cols, "stride": stride, "head": st["head"], "viewport": st["viewport"],
           "offset": st["offset"]}
    geo_ref = use_ref(geo)
    geo_ref.current = geo
    use_imperative_handle(ref, lambda: FlatListHandle(sref, lambda: geo_ref.current), [])

    ae = on_scroll if getattr(on_scroll, "_is_animated_event", False) else None

    def min_rows() -> int:
        return int(initial_num_to_render) if meas["sizes"] else shown

    def span(offset: float, viewport: float, head: float) -> tuple:
        if windowed:
            return window_range(offset - head, viewport, stride, rows, window_size)
        return measured_range(offset - head, viewport, meas["sizes"], rows, window_size, min_rows())[:2]

    def on_scroll_evt(e: Dict[str, Any]) -> None:
        off = e["x"] if horizontal else e["y"]
        vp = e["width"] if horizontal else e["height"]
        ct = e["content_width"] if horizontal else e["content_height"]

        def upd(s: Dict[str, Any]) -> Dict[str, Any]:  # several events can land before the next render
            moved = span(off, vp, s["head"]) != (meas["first"], meas["last"])
            if moved or vp != s["viewport"] or ct != s["content"]:
                return {**s, "offset": float(off), "viewport": float(vp), "content": float(ct)}
            return s

        set_st(upd)
        if not windowed and not meas["sizes"] and off + vp >= ct - vp * 1.5 and shown < rows:
            set_shown(lambda s: s + max_to_render_per_batch if s == shown else s)
        if on_end_reached is not None and ct > 0:
            key = (n, ct)
            if off + vp >= ct - vp * on_end_reached_threshold and fired.current != key:
                fired.current = key
                on_end_reached({"distanceFromEnd": ct - off - vp})
        if ae is not None:
            if not ae.native:
                ae(e)
            elif ae.listener is not None:
                ae.listener(e)
        elif on_scroll is not None:
            on_scroll(e)

    def on_head_layout(e: Dict[str, Any]) -> None:
        h = float(e[prop])
        set_st(lambda s: s if s["head"] == h else {**s, "head": h})

    def row_layout(r: int) -> Callable[[Dict[str, Any]], None]:
        fn = meas["handlers"].get(r)
        if fn is None:
            def fn(e: Dict[str, Any]) -> None:
                v = float(e[prop])
                if meas["sizes"].get(r) == v:
                    return
                meas["sizes"][r] = v
                s = geo_ref.current
                # rows above the window shift the top spacer; others matter only when they move the window
                if r < meas["first"] or measured_range(
                        s["offset"] - s["head"], s["viewport"], meas["sizes"], rows, window_size,
                        min_rows())[:2] != (meas["first"], meas["last"]):
                    set_ver(lambda x: x + 1)
            meas["handlers"][r] = fn
        return fn

    def cell(i: int) -> Any:
        return render_item({"item": data[i], "index": i, "separators": _SEPARATORS})

    out: List[Any] = []
    if list_header_component is not None:
        out.append(View(_node(list_header_component), on_layout=on_head_layout, key="__head"))

    if n == 0:
        if list_empty_component is not None:
            out.append(View(_node(list_empty_component), key="__empty"))
    else:
        if windowed:
            first, last = span(st["offset"], st["viewport"], st["head"])
            top, bottom = first * stride, (rows - last) * stride
        else:
            first, last, top, bottom = measured_range(st["offset"] - st["head"], st["viewport"], meas["sizes"], rows,
                                                      window_size, min_rows())
        meas["first"], meas["last"] = first, last
        if first > 0:
            out.append(View(style={prop: top}, key="__top"))
        for r in range(first, last):
            fixed = {prop: length} if windowed else {}
            lay = {} if windowed else {"on_layout": row_layout(r)}
            if cols == 1:
                out.append(View(cell(r), style=fixed, key=_key_of(data[r], r, key_extractor), **lay))
            else:
                cells = []
                for c in range(cols):
                    i = r * cols + c
                    # Equal columns. The cell is a row, like RN's column wrapper the item sits in, so an item
                    # styled {"flex": 1} fills the column's width instead of collapsing to zero height.
                    cells.append(View(cell(i), style={"flex": 1, "flex_direction": "row"},
                                      key=_key_of(data[i], i, key_extractor))
                                 if i < n else View(style={"flex": 1}, key="pad%d" % c))
                out.append(View(*cells, style=[{"flex_direction": "row"}, column_wrapper_style, fixed],
                                key="r%d" % r, **lay))
            if item_separator_component is not None and r < rows - 1:
                out.append(View(_node(item_separator_component), key="s%d" % r))
        if last < rows and bottom > 0:
            out.append(View(style={prop: bottom}, key="__bottom"))

    if list_footer_component is not None:
        out.append(View(_node(list_footer_component), key="__foot"))

    handler: Any = on_scroll_evt
    if ae is not None and ae.native:
        from ..animated.api import AnimatedEvent
        handler = AnimatedEvent(ae.map, listener=on_scroll_evt, use_native_driver=True)
    if on_refresh is not None:
        props["refresh_control"] = RefreshControl(refreshing=bool(refreshing), on_refresh=on_refresh)
    return ScrollView(*out, horizontal=horizontal, style=style, content_container_style=content_container_style,
                      on_scroll=handler, ref=sref, **props)


@component
def SectionList(sections: Optional[List[Dict[str, Any]]] = None, render_item: Optional[Callable] = None,
                render_section_header: Optional[Callable] = None, render_section_footer: Optional[Callable] = None,
                key_extractor: Optional[Callable[[Any, int], Any]] = None, **props: Any):
    """RN SectionList: `sections=[{"title", "data", "renderItem"?, "keyExtractor"?}]`. `renderItem` gets
    `{"item", "index", "section", "separators"}`; the section renderers get `{"section"}`. Sticky headers are not
    supported yet."""
    props.pop("sticky_section_headers_enabled", None)
    props.pop("section_separator_component", None)
    rows: List[Any] = []
    for si, sec in enumerate(sections or []):
        if render_section_header is not None:
            rows.append(("h", si, sec, None, 0))
        for ii, item in enumerate(sec.get("data") or []):
            rows.append(("i", si, sec, item, ii))
        if render_section_footer is not None:
            rows.append(("f", si, sec, None, 0))

    def render(arg: Any) -> Any:
        kind, si, sec, item, ii = arg["item"]
        if kind == "h":
            return render_section_header({"section": sec})
        if kind == "f":
            return render_section_footer({"section": sec})
        fn = sec.get("renderItem") or sec.get("render_item") or render_item
        if fn is None:
            raise TypeError("SectionList needs renderItem (or a renderItem on the section)")
        return fn({"item": item, "index": ii, "section": sec, "separators": _SEPARATORS})

    def key(row: Any, _i: int) -> Any:
        kind, si, sec, item, ii = row
        if kind != "i":
            return (kind, si)
        ke = sec.get("keyExtractor") or sec.get("key_extractor") or key_extractor
        return ("i", si, _key_of(item, ii, ke))

    return FlatList(data=rows, render_item=render, key_extractor=key, **props)


@component
def VirtualizedList(data: Any = None, get_item: Optional[Callable] = None, get_item_count: Optional[Callable] = None,
                    render_item: Optional[Callable] = None, **props: Any):
    """RN VirtualizedList: FlatList over any `data` read through `getItem(data, index)` / `getItemCount(data)`."""
    count = get_item_count(data) if get_item_count else len(data or [])
    items = [get_item(data, i) if get_item else data[i] for i in range(count)]
    return FlatList(data=items, render_item=render_item, **props)
