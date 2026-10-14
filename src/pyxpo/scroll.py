"""Scroll helpers: ScrollRef (imperative scroll_to) and FlatList (windowed list built on ScrollView)."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from . import modules
from .component import component
from .element import ScrollView, View
from .env import use_window_dimensions
from .hooks import use_memo, use_ref, use_state


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


def _takes_one(fn: Callable) -> bool:
    """True when `fn` declares exactly one positional parameter (RN style `({item, index}) => ...`)."""
    code = getattr(fn, "__code__", None)
    if code is None:
        import inspect
        try:
            ps = [p for p in inspect.signature(fn).parameters.values()
                  if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
            var = any(p.kind == p.VAR_POSITIONAL for p in inspect.signature(fn).parameters.values())
        except (TypeError, ValueError):
            return False
        return len(ps) == 1 and not var
    return code.co_argcount - (1 if hasattr(fn, "__self__") else 0) == 1 and not code.co_flags & 0x04


def adapt_render_item(fn: Callable) -> Callable[[Any, int], Any]:
    """`render_item(item, index)` stays as is; a one-parameter function gets `{"item", "index"}` like React Native."""
    if _takes_one(fn):
        return lambda item, index: fn({"item": item, "index": index})
    return fn


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
    if render_item is not None:
        render_item = adapt_render_item(render_item)
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
        # re-render only when the rendered window changes, not on every scroll tick. Functional update:
        # several events can land before the next render, so `st` from this closure may be stale.
        def upd(s: Dict[str, Any]) -> Dict[str, Any]:
            moved = (span(off, vp, s["head"]) != span(s["offset"], s["viewport"], s["head"])
                     if item_size is not None else False)
            if moved or vp != s["viewport"] or ct != s["content"]:
                return {**s, "offset": float(off), "viewport": float(vp), "content": float(ct)}
            return s

        set_st(upd)
        if on_end_reached is not None and ct > 0:
            key = (n, ct)
            if off + vp >= ct - vp * on_end_reached_threshold and fired.current != key:
                fired.current = key
                on_end_reached()
        if item_size is None and off + vp >= ct - vp * 1.5 and shown < rows:
            set_shown(lambda s: s + batch_size if s == shown else s)  # one batch per rendered state
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


@component
def SectionList(sections: Optional[List[Dict[str, Any]]] = None, render_item: Optional[Callable] = None,
                render_section_header: Optional[Callable] = None, render_section_footer: Optional[Callable] = None,
                key_extractor: Optional[Callable[[Any, int], Any]] = None, **props: Any):
    """Sectioned list: `sections=[{"title": ..., "data": [...]}]`, built on FlatList (no sticky headers).

    `render_item` takes `(item, index)` or one `{"item", "index", "section"}` dict; the section renderers take one
    `{"section"}` dict. A section may carry its own `render_item` and `key_extractor`.
    """
    rows: List[Any] = []
    for si, sec in enumerate(sections or []):
        if render_section_header is not None:
            rows.append(("h", si, sec, None, 0))
        for ii, item in enumerate(sec.get("data") or []):
            rows.append(("i", si, sec, item, ii))
        if render_section_footer is not None:
            rows.append(("f", si, sec, None, 0))

    def render(row: Any, _i: int) -> Any:
        kind, si, sec, item, ii = row
        if kind == "h":
            return render_section_header({"section": sec})
        if kind == "f":
            return render_section_footer({"section": sec})
        fn = sec.get("render_item") or sec.get("renderItem") or render_item
        if fn is None:
            raise TypeError("SectionList needs render_item (or a render_item on the section)")
        if _takes_one(fn):
            return fn({"item": item, "index": ii, "section": sec})
        return fn(item, ii)

    def key(row: Any, _i: int) -> Any:
        kind, si, sec, item, ii = row
        if kind != "i":
            return (kind, si)
        ke = sec.get("key_extractor") or sec.get("keyExtractor") or key_extractor
        return ("i", si, _key_of(item, ii, ke))

    return FlatList(data=rows, render_item=render, key_extractor=key, **props)

