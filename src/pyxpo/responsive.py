"""Responsive breakpoints, like CSS media queries, on every platform.

The window width picks the active breakpoint (mobile first, Bootstrap 5 widths by default):

    xs 0   sm 576   md 768   lg 992   xl 1200   xxl 1400

A breakpoint map is a dict whose keys are all breakpoint names (`"base"` is an alias of the smallest one). It
resolves to the value of the largest breakpoint at or below the active one, so `{"base": 1, "md": 3}` is 1 on a
phone and 3 from 768 dp up. Maps work in three places:

- a style value: `style={"padding": {"base": 8, "lg": 24}, "flex_direction": {"base": "column", "md": "row"}}`
- a whole style block, merged up to the active breakpoint (like Tailwind's `md:`):
  `style={"base": {"padding": 8}, "md": {"padding": 24, "flex_direction": "row"}}`
- any value, through `use_breakpoint_value(map)` in a component

Responsive styles are resolved by the reconciler: when the window crosses a breakpoint only the views whose style
holds a map are updated, with no re-render. Hooks re-render only when the breakpoint (or the query result) changes.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

DEFAULT_BREAKPOINTS: Dict[str, int] = {"xs": 0, "sm": 576, "md": 768, "lg": 992, "xl": 1200, "xxl": 1400}

_order: List[Tuple[str, int]] = []
_names: frozenset = frozenset()
_rank: Dict[str, int] = {}
_version = 0  # bumped by set_breakpoints: resolved styles cached against an older table are stale


def set_breakpoints(table: Optional[Dict[str, int]] = None) -> None:
    """Replaces the breakpoint table, e.g. `{"phone": 0, "tablet": 600, "desktop": 1024}`. None restores the
    default. Call it before the app renders (the `[tool.pyxpo] breakpoints` config does this for you)."""
    global _order, _names, _rank, _version
    table = dict(DEFAULT_BREAKPOINTS if table is None else table)
    if not table:
        raise ValueError("breakpoints: at least one breakpoint is needed")
    for name, width in table.items():
        if not isinstance(name, str) or not name or name == "base":
            raise ValueError("breakpoints: bad name %r ('base' is reserved)" % (name,))
        if isinstance(width, bool) or not isinstance(width, (int, float)) or width < 0:
            raise ValueError("breakpoints: %r must be a width >= 0, got %r" % (name, width))
    _order = sorted(table.items(), key=lambda kv: kv[1])
    if _order[0][1] != 0:
        _order[0] = (_order[0][0], 0)  # the smallest breakpoint covers every width below the next one
    _names = frozenset(table) | {"base"}
    _rank = {n: i for i, (n, _) in enumerate(_order)}
    _rank["base"] = 0
    _version += 1


set_breakpoints()


def breakpoints() -> Dict[str, int]:
    """The active table, smallest first: `{"xs": 0, "sm": 576, ...}`."""
    return dict(_order)


def breakpoint_for(width: float) -> str:
    """Name of the breakpoint a window `width` (dp) falls in."""
    name = _order[0][0]
    for n, w in _order:
        if width >= w:
            name = n
        else:
            break
    return name


def _check(name: str) -> int:
    r = _rank.get(name)
    if r is None:
        raise ValueError("unknown breakpoint %r (have %s)" % (name, ", ".join(n for n, _ in _order)))
    return r


def up(name: str, bp: str) -> bool:
    """True when breakpoint `bp` is `name` or wider (CSS `min-width`)."""
    return _check(bp) >= _check(name)


def down(name: str, bp: str) -> bool:
    """True when breakpoint `bp` is narrower than `name` (CSS `max-width: name - 0.02px`)."""
    return _check(bp) < _check(name)


def between(lo: str, hi: str, bp: str) -> bool:
    """True when `lo <= bp < hi`."""
    return up(lo, bp) and down(hi, bp)


def is_map(v: Any) -> bool:
    """True for a breakpoint map: a non-empty dict whose keys are all breakpoint names."""
    return v.__class__ is dict and bool(v) and _names.issuperset(v)


def pick(value: Any, bp: str, default: Any = None) -> Any:
    """The value of a breakpoint map at breakpoint `bp` (mobile first). Anything else is returned as is."""
    if not is_map(value):
        return value
    r = _check(bp)
    best, best_rank = default, -1
    for k, v in value.items():
        kr = _rank[k]
        if best_rank < kr <= r:
            best, best_rank = v, kr
    return best


def _blocks(style: Dict[str, Any], r: int) -> Dict[str, Any]:
    """Plain keys first, then each breakpoint block up to rank `r`, smallest first (later wins, like CSS)."""
    out = {k: v for k, v in style.items() if k not in _names}
    for k in sorted((k for k in style if k in _names and _rank[k] <= r), key=_rank.__getitem__):
        block = style[k]
        if block is None or block is False:
            continue
        if not isinstance(block, dict):
            raise TypeError("responsive style block %r must be a style dict, got %r" % (k, type(block).__name__))
        out.update(block)
    return out


def resolve_style(style: Any, bp: str) -> Tuple[Any, bool]:
    """(style with every breakpoint map resolved at `bp`, whether it held any map). A style without maps comes back
    as the same object, so the normalize cache and the reconciler's identity checks keep working."""
    if style.__class__ is dict:
        if not style:
            return style, False
        for k in style:
            if k in _names:
                return resolve_style(_blocks(style, _check(bp)), bp)[0], True
        for v in style.values():
            if v.__class__ is dict and v and _names.issuperset(v):
                break
        else:
            return style, False
        return {k: pick(v, bp) for k, v in style.items()}, True
    if isinstance(style, (list, tuple)):
        used = False
        parts = []
        for s in style:
            s2, u = resolve_style(s, bp)
            used = used or u
            parts.append(s2)
        return (parts if used else style), used
    return style, False


def current() -> str:
    """Breakpoint of the running app's window, read once (not reactive: components use `use_breakpoint`)."""
    from .apis import _env
    return breakpoint_for(_env.current._data["window"]["width"] or 0)


def query(bp: str, width: float, height: float, *, up_: Optional[str] = None, down_: Optional[str] = None,
          only: Optional[str] = None, min_width: Optional[float] = None, max_width: Optional[float] = None,
          orientation: Optional[str] = None) -> bool:
    """Media query test against one window; every given condition must hold."""
    if up_ is not None and not up(up_, bp):
        return False
    if down_ is not None and not down(down_, bp):
        return False
    if only is not None and _check(only) != _check(bp):
        return False
    if min_width is not None and width < min_width:
        return False
    if max_width is not None and width > max_width:
        return False
    if orientation is not None:
        if orientation not in ("portrait", "landscape"):
            raise ValueError("orientation must be 'portrait' or 'landscape', got %r" % (orientation,))
        if (width > height) != (orientation == "landscape"):
            return False
    return True


def names() -> Iterable[str]:
    return [n for n, _ in _order]


def version() -> int:
    return _version
