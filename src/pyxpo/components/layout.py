"""Layout primitives on top of flexbox, the same on every platform: Container, Row/Col (12-column grid), Grid,
Flex/HStack/VStack/Center/Spacer and Show/Hide.

Every sizing prop takes a plain value or a breakpoint map (`{"base": 12, "md": 6}`, see `pyxpo.responsive`). Maps
become responsive styles, so crossing a breakpoint re-styles the views without re-rendering the component.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .. import responsive
from ..component import component
from ..element import Element, flatten as flatten_children
from ..hooks import create_context, use_context, use_media_query, use_state
from .view import View

GridContext = create_context(None)  # {"gx": gutter or map, "columns": n} for Col inside a Row

CONTAINER_MAX = {"sm": 540, "md": 720, "lg": 960, "xl": 1140, "xxl": 1320}  # Bootstrap 5 container widths


def _pct(n: float, of: float) -> str:
    v = round(100.0 * n / of, 4)
    return ("%d%%" % v) if v == int(v) else ("%s%%" % v)


def _per_bp(value: Any, make: Callable[[Any], Dict[str, Any]]) -> Dict[str, Any]:
    """`make(v)` for a plain value; a breakpoint block map {bp: make(v)} for a map."""
    if responsive.is_map(value):
        return {bp: make(v) for bp, v in value.items()}
    return make(value)


def _map(value: Any, fn: Callable[[Any], Any]) -> Any:
    """fn applied to a plain value or to each value of a breakpoint map."""
    if responsive.is_map(value):
        return {bp: fn(v) for bp, v in value.items()}
    return fn(value)


def _half(v: Any) -> Any:
    return None if v is None else v / 2.0


def _neg_half(v: Any) -> Any:
    return None if v is None else -v / 2.0


# -- Container -------------------------------------------------------------------------------------------------------
@component
def Container(*children: Any, fluid: Any = False, max_width: Any = None, padding: Any = 16, style: Any = None,
              **props: Any):
    """Centered page column. Its max width steps up with the breakpoint (540, 720, 960, 1140, 1320 like Bootstrap);
    `fluid=True` (or a breakpoint name such as "lg": fluid below it) keeps it full width. `max_width` takes a
    number or a breakpoint map. `padding` is the side gutter."""
    if max_width is None:
        names = list(responsive.names())
        if fluid is True:
            mw: Any = None
        else:
            stop = responsive._check(fluid) if isinstance(fluid, str) else 0
            mw = {"base": None}
            for bp, w in CONTAINER_MAX.items():
                if bp in names and responsive._check(bp) >= stop:
                    mw[bp] = w
            if len(mw) == 1:
                mw = None
    else:
        mw = max_width
    base = {"width": "100%", "align_self": "center", "max_width": mw, "padding_horizontal": padding}
    return View(*children, style=[base, style], **props)


# -- Row / Col -------------------------------------------------------------------------------------------------------
@component
def Row(*children: Any, gutter: Any = 16, gx: Any = None, gy: Any = None, columns: int = 12, align: Any = None,
        justify: Any = None, wrap: bool = True, style: Any = None, **props: Any):
    """Row of a 12-column grid (Bootstrap style). `Col(span=6)` children take 6/12 of the width and wrap to the next
    line when the row is full. `gutter` is the space between columns and between lines; `gx` / `gy` set them
    separately. `align` / `justify` are align_items / justify_content. All take breakpoint maps."""
    hx = gutter if gx is None else gx
    vy = gutter if gy is None else gy
    st = {"flex_direction": "row", "flex_wrap": "wrap" if wrap else "nowrap",
          "margin_horizontal": _map(hx, _neg_half), "row_gap": vy,
          "align_items": align, "justify_content": justify}
    ctx = {"gx": hx, "columns": columns}
    return GridContext.Provider(View(*children, style=[st, style], **props), value=ctx)


def _col_size(span: Any, columns: int) -> Dict[str, Any]:
    if span is None or span is True:  # equal share of the row
        return {"display": "flex", "flex_grow": 1, "flex_shrink": 1, "flex_basis": 0, "width": None,
                "max_width": None}
    if span == "auto":  # as wide as its content
        return {"display": "flex", "flex_grow": 0, "flex_shrink": 0, "flex_basis": "auto", "width": "auto",
                "max_width": None}
    if isinstance(span, bool) or not isinstance(span, (int, float)) or span < 0:
        raise ValueError("Col span must be a number of columns, 'auto' or None, got %r" % (span,))
    if span == 0:
        return {"display": "none"}
    w = _pct(min(span, columns), columns)
    return {"display": "flex", "flex_grow": 0, "flex_shrink": 0, "flex_basis": "auto", "width": w, "max_width": w}


@component
def Col(*children: Any, span: Any = None, offset: Any = None, align: Any = None,
        style: Any = None, **props: Any):
    """Column inside a `Row`. `span`: columns of 12 (`span={"base": 12, "md": 6, "xl": 4}`), "auto" (content width)
    or None (equal share). `span=0` hides it at that breakpoint. `offset` skips columns on the left. `align` is
    align_self."""
    ctx = use_context(GridContext) or {"gx": 0, "columns": 12}
    columns = ctx["columns"]
    size = _per_bp(span, lambda v: _col_size(v, columns))
    if responsive.is_map(span) and "base" not in span and not any(responsive._check(k) == 0 for k in span):
        size = dict(size, base=_col_size(columns, columns))  # below the first breakpoint: full width (Bootstrap)
    st: List[Any] = [size, {"padding_horizontal": _map(ctx["gx"], _half), "align_self": align}]
    if offset is not None:
        st.append({"margin_left": _map(offset, lambda v: _pct(v, columns) if v else 0)})
    st.append(style)
    return View(*children, style=st, **props)


# -- Grid ------------------------------------------------------------------------------------------------------------
@component
def GridItem(*children: Any, span: Any = 1, style: Any = None, **props: Any):
    """Cell of a `Grid` spanning `span` columns (a number or breakpoint map). The Grid sizes it."""
    return View(*children, style=style, **props)


@component
def Grid(*children: Any, columns: Any = None, gap: Any = 16, row_gap: Any = None, column_gap: Any = None,
         min_item_width: Optional[float] = None, align: Any = None, style: Any = None, **props: Any):
    """Equal-width columns that wrap into rows, like CSS grid `repeat(n, 1fr)`.

    `columns`: a number or a breakpoint map (`{"base": 1, "sm": 2, "lg": 4}`). `min_item_width`: auto-fit as many
    columns of at least that width as the grid's own width allows (CSS `repeat(auto-fill, minmax(w, 1fr))`).
    `gap` / `row_gap` / `column_gap` space the cells. Wrap a child in `GridItem(span=2)` to span columns.
    `align` is align_items for each row (default stretch: cells in a row share its height)."""
    measured, set_measured = use_state(0.0)
    cg = gap if column_gap is None else column_gap
    rg = gap if row_gap is None else row_gap
    if min_item_width is not None:
        if columns is None:
            g = responsive.pick(cg, responsive.current(), 0) or 0  # n cells fit when n*w + (n-1)*g <= width
            columns = max(1, int((measured + g) // (min_item_width + g))) if measured else 1
    elif columns is None:
        columns = 1
    cells = []
    for i, child in enumerate(flatten_children(children)):
        span = 1
        if isinstance(child, Element) and getattr(child.type, "_target", None) is GridItem:
            span = child.props.get("span", 1)
        cell_style = _per_bp(_zip(columns, span), lambda cs: _cell(cs[0], cs[1]))
        cells.append(View(child, key=child.key if isinstance(child, Element) and child.key is not None else i,
                          style=[cell_style, {"padding_horizontal": _map(cg, _half)}]))
    st = {"flex_direction": "row", "flex_wrap": "wrap", "margin_horizontal": _map(cg, _neg_half), "row_gap": rg,
          "align_items": align}
    on_layout = props.pop("on_layout", None)
    if min_item_width is not None:
        def measure(e: Dict[str, Any]) -> None:
            set_measured(float(e["width"]))
            if on_layout is not None:
                on_layout(e)
        on_layout = measure
    return View(View(*cells, style=st), style=style, on_layout=on_layout, **props)


def _zip(columns: Any, span: Any) -> Any:
    """(columns, span) per breakpoint, as a breakpoint map when either is one."""
    if not responsive.is_map(columns) and not responsive.is_map(span):
        return (columns, span)
    keys = set(columns if responsive.is_map(columns) else ()) | set(span if responsive.is_map(span) else ())
    out = {}
    for k in keys:
        out[k] = (responsive.pick(columns, k, 1), responsive.pick(span, k, 1))
    return out


def _cell(columns: Any, span: Any) -> Dict[str, Any]:
    if isinstance(columns, bool) or not isinstance(columns, int) or columns < 1:
        raise ValueError("Grid columns must be a whole number >= 1, got %r" % (columns,))
    w = _pct(min(max(span, 1), columns), columns)
    return {"width": w, "max_width": w, "flex_grow": 0, "flex_shrink": 0}


# -- Flex helpers ----------------------------------------------------------------------------------------------------
@component
def Flex(*children: Any, direction: Any = "row", gap: Any = None, align: Any = None, justify: Any = None,
         wrap: Any = None, grow: Any = None, style: Any = None, **props: Any):
    """Flexbox container with short props: `direction` ("row", "column", "row_reverse", "column_reverse"), `gap`,
    `align` (align_items), `justify` (justify_content), `wrap` (True / "wrap" / "nowrap"), `grow` (flex). Each takes
    a breakpoint map: `Flex(direction={"base": "column", "md": "row"})` stacks on phones and lines up on wider
    screens."""
    st = {"flex_direction": direction, "gap": gap, "align_items": align, "justify_content": justify,
          "flex_wrap": _map(wrap, lambda w: "wrap" if w is True else ("nowrap" if w is False else w)),
          "flex": grow}
    return View(*children, style=[st, style], **props)


@component
def HStack(*children: Any, spacing: Any = 8, align: Any = "center", justify: Any = None, wrap: Any = None,
           style: Any = None, **props: Any):
    """Children side by side, `spacing` apart, vertically centered."""
    return Flex(*children, direction="row", gap=spacing, align=align, justify=justify, wrap=wrap, style=style,
                **props)


@component
def VStack(*children: Any, spacing: Any = 8, align: Any = None, justify: Any = None, style: Any = None,
           **props: Any):
    """Children stacked top to bottom, `spacing` apart."""
    return Flex(*children, direction="column", gap=spacing, align=align, justify=justify, style=style, **props)


@component
def Center(*children: Any, style: Any = None, **props: Any):
    """Centers its children on both axes."""
    return View(*children, style=[{"align_items": "center", "justify_content": "center"}, style], **props)


@component
def Spacer(size: Any = None, style: Any = None, **props: Any):
    """Takes the free space in a Flex/HStack/VStack (or a fixed `size` in dp)."""
    st = {"flex": 1} if size is None else {"width": size, "height": size, "flex_shrink": 0}
    return View(style=[st, style], **props)


# -- Show / Hide -----------------------------------------------------------------------------------------------------
def _check_query(above: Any, below: Any, only: Any) -> None:
    if above is None and below is None and only is None:
        raise TypeError("give above=, below= or only= (a breakpoint name)")


@component
def Show(*children: Any, above: Optional[str] = None, below: Optional[str] = None, only: Optional[str] = None):
    """Renders its children only at matching breakpoints: `Show(Sidebar(), above="lg")` from lg up,
    `below="md"` under md, `only="md"`. Hidden children are unmounted (use a `display` breakpoint map in a style to
    keep them mounted)."""
    _check_query(above, below, only)
    hit = use_media_query(above, below, only=only)
    return list(children) if hit else None


@component
def Hide(*children: Any, above: Optional[str] = None, below: Optional[str] = None, only: Optional[str] = None):
    """The opposite of `Show`: hides its children at matching breakpoints."""
    _check_query(above, below, only)
    hit = use_media_query(above, below, only=only)
    return None if hit else list(children)


__all__ = ["Container", "Row", "Col", "Grid", "GridItem", "Flex", "HStack", "VStack", "Center", "Spacer", "Show",
           "Hide", "GridContext"]
