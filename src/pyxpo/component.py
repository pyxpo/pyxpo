from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional, Tuple

from ._keys import alias_props, prop_name
from .element import Element, flatten


class Component:
    """A function component. Calling it builds an Element; the fn runs during reconciliation."""

    _boundary = False  # ErrorBoundary: the reconciler catches render errors below it

    def __init__(self, fn: Callable[..., Any], name: str = "") -> None:
        self.fn = fn
        self.name = name or getattr(fn, "__name__", "Component")
        self.memo: Optional[Callable[[Element, Element], bool]] = None  # (old, new) -> True to skip re-render
        self._target: "Component" = self  # memo() wrappers point at the wrapped component
        self._params: Optional[frozenset] = None

    def __call__(self, *children: Any, key: Any = None, **props: Any) -> Element:
        if props and not "".join(props).islower():
            props = self._alias(props)
        return Element(self, props, flatten(children), key)

    def _alias(self, props: Dict[str, Any]) -> Dict[str, Any]:
        """RN spellings (`onPress`) -> pyxpo ones. Built-ins convert every key. A user component converts a key only
        when its snake_case form is an explicit parameter (so `def Card(onPress=None)` keeps its own names)."""
        t = self._target
        fn = t.fn
        mod = getattr(fn, "__module__", "") or ""
        if mod == "pyxpo" or mod.startswith("pyxpo."):
            return alias_props(props)
        if t._params is None:
            import inspect
            try:
                t._params = frozenset(inspect.signature(fn).parameters)
            except (TypeError, ValueError):
                t._params = frozenset()
        params = t._params
        out: Dict[str, Any] = {}
        for k, v in props.items():
            n = prop_name(k) if (k not in params and prop_name(k) in params) else k
            if n in out or (n != k and n in props):
                raise TypeError("got both %r and %r" % (k, n))
            out[n] = v
        return out

    def __repr__(self) -> str:
        return "<Component %s>" % self.name


# Hot reload keeps Component identity across module re-execution: a re-run @component returns the
# existing object (keyed by source file + qualname) so the reconciler keeps matching fibers.
_Key = Tuple[str, str]
_registry: Dict[_Key, Component] = {}
_on = False
_pending: Optional[Dict[_Key, Callable[..., Any]]] = None
_added: List[_Key] = []


def enable_registry(on: bool = True) -> None:
    global _on
    _on = on
    if not on:
        _registry.clear()


def _key(fn: Callable[..., Any]) -> Optional[_Key]:
    code = getattr(fn, "__code__", None)
    qual = getattr(fn, "__qualname__", "")
    if code is None or not qual or "<locals>" in qual:
        return None
    return os.path.realpath(code.co_filename), qual


def begin_swap() -> None:
    global _pending
    _pending = {}
    del _added[:]


def commit_swap() -> int:
    global _pending
    pending, _pending = _pending or {}, None
    for k, fn in pending.items():
        c = _registry[k]
        c.fn = fn
        c._params = None
    del _added[:]
    return len(pending)


def abort_swap() -> None:
    global _pending
    _pending = None
    for k in _added:
        _registry.pop(k, None)
    del _added[:]


def component(fn: Callable[..., Any]) -> Component:
    k = _key(fn) if _on else None
    if k is None:
        return Component(fn)
    existing = _registry.get(k)
    if existing is None:
        _registry[k] = c = Component(fn)
        if _pending is not None:
            _added.append(k)
        return c
    if _pending is not None:
        _pending[k] = fn
    else:
        existing.fn = fn
        existing._params = None
    return existing


def _props_equal(old: Element, new: Element) -> bool:
    from .hooks import _same
    if old.props.keys() != new.props.keys() or len(old.children) != len(new.children):
        return False
    return (all(_same(v, new.props[k]) for k, v in old.props.items())
            and all(_same(a, b) for a, b in zip(old.children, new.children)))


def memo(comp: Component, are_equal: Optional[Callable[[Dict[str, Any], Dict[str, Any]], bool]] = None) -> Component:
    """Skip re-rendering `comp` when its props are unchanged (shallow ==). Use `use_callback` for handlers.

    A component that reads context (or has a descendant that does) is never skipped, so theme and
    navigation updates still reach it. `are_equal(old_props, new_props)` overrides the comparison."""
    out = Component(lambda *a, **k: comp.fn(*a, **k), name=comp.name)  # late-bound: hot reload swaps comp.fn
    out._target = comp._target
    if are_equal is None:
        out.memo = _props_equal
    else:
        out.memo = lambda old, new: bool(are_equal(old.props, new.props))
    return out


# -- ErrorBoundary ---------------------------------------------------------
class _BoundaryCell:
    __slots__ = ("error", "showing", "reset")


def _boundary_cell(f: Any) -> _BoundaryCell:
    cell = _BoundaryCell()
    cell.error = None
    cell.showing = False  # the current children are the fallback

    def reset() -> None:
        if cell.error is not None and not f.unmounted:
            cell.error = None
            f.rec.schedule(f)

    cell.reset = reset
    return cell


def _error_boundary(*children: Any, fallback: Any = None, on_error: Optional[Callable[[BaseException], Any]] = None):
    from .hooks import _use
    cell, _ = _use("boundary", _boundary_cell)  # must stay the first hook: the reconciler reads hooks[0]
    if cell.error is None:
        return list(children)
    if callable(fallback) and not isinstance(fallback, Element):
        return fallback(cell.error, cell.reset)
    return fallback


ErrorBoundary = Component(_error_boundary, name="ErrorBoundary")
ErrorBoundary.__doc__ = """`ErrorBoundary(*children, fallback=lambda error, reset: ..., on_error=None)`.

A render error in any child (mount or update) rolls that subtree back and renders `fallback(error, reset)` (or
`fallback` itself when it is an element; nothing when None). `reset()` renders the children again. `on_error(error)`
is called once per caught error. Like React, only render errors are caught: event handler and effect errors go to
`App.on_error`. An error inside the fallback goes to the next boundary up."""
ErrorBoundary._boundary = True
