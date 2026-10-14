from __future__ import annotations

import os
import inspect
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .element import Element, flatten
from . import env as _env_mod
from .hooks import _same, render_with_hooks
from .style import flatten as flatten_style, normalize as normalize_style
from .ops import Create, Delete, Insert, Op, Remove, Update


class Fiber:
    def __init__(self, kind: str, element: Optional[Element], parent: Optional["Fiber"], rec: "Reconciler") -> None:
        self.kind = kind  # "root" | "host" | "comp"
        self.element = element
        self.parent = parent
        self.rec = rec
        self.key = element.key if element is not None else None
        self.depth = parent.depth + 1 if parent is not None else 0
        self.children: List[Fiber] = []
        self.id: Optional[int] = None
        self.sent: Dict[str, Any] = {}  # last props sent to native (host)
        self.events: Set[str] = set()
        self.native: List[int] = []  # ids of native children currently attached (host/root)
        self.hooks: List[Tuple[str, Any]] = []
        self.hook_index = 0
        self.hooks_ready = False
        self.unmounted = False


def _host_children(fiber: Fiber) -> List[Fiber]:
    out: List[Fiber] = []
    for c in fiber.children:
        if c.kind == "comp":
            out.extend(_host_children(c))
        else:
            out.append(c)
    return out


class Reconciler:
    """Diffs element trees into a flat list of native ops. One commit = one ops list."""

    def __init__(self, schedule: Optional[Callable[[Fiber], None]] = None) -> None:
        self._schedule = schedule
        self.loop: Any = None
        self.env = _env_mod.Env()
        self.wire_v2 = os.environ.get("PYXPO_WIRE") == "2"  # native understands normalized styles (ARGB ints)
        self.ops: List[Op] = []
        self.pending_effects: List[Tuple[Fiber, Any, Callable[[], Any]]] = []
        self.handlers: Dict[Tuple[int, str], Callable[..., Any]] = {}
        self._deletes: List[int] = []
        self._next_id = 2
        self.root = Fiber("root", None, None, self)
        self.root.id = 1

    # -- public --------------------------------------------------------
    def schedule(self, fiber: Fiber) -> None:
        if self._schedule is not None:
            self._schedule(fiber)

    def render(self, element: Element) -> None:
        self._reconcile_children(self.root, flatten([element]))
        self._sync(self.root)

    def update(self, fiber: Fiber) -> None:
        if fiber.unmounted:
            return
        self._render_comp(fiber)
        host = fiber.parent
        while host.kind == "comp":
            host = host.parent
        self._sync(host)

    def take_ops(self) -> List[Op]:
        from .animated import runtime as _anim
        ops = _anim.drain() + self.ops
        ops.extend(Delete(i) for i in self._deletes)
        self.ops, self._deletes = [], []
        return ops

    def run_effects(self) -> None:
        pending, self.pending_effects = self.pending_effects, []
        live = [p for p in pending if not p[0].unmounted]
        for _, cell, _fn in live:
            if cell.cleanup:
                cleanup, cell.cleanup = cell.cleanup, None
                cleanup()
        for _, cell, fn in live:
            result = fn()
            cell.cleanup = result if callable(result) else None

    def dispatch(self, node_id: int, event: str, payload: Optional[Dict[str, Any]] = None) -> bool:
        fn = self.handlers.get((node_id, event))
        if fn is None:
            return False
        payload = payload or {}
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            sig = None
        if sig is not None and payload:
            try:
                sig.bind(payload.get("value"))
                fn(payload.get("value"))
                return True
            except TypeError as e:
                if "argument" not in str(e):
                    raise
        fn()
        return True

    # -- internals -----------------------------------------------------
    def _wire(self, props: Dict[str, Any]):
        wire: Dict[str, Any] = {}
        events: Dict[str, Callable[..., Any]] = {}
        for k, v in props.items():
            if k == "style":
                if self.wire_v2:
                    v = normalize_style(v)
                else:
                    if isinstance(v, (list, tuple)):
                        v = flatten_style(v)
                    if isinstance(v, dict) and any(getattr(x, "_is_animated", False) for x in v.values()):
                        v = {a: (x._wire() if getattr(x, "_is_animated", False) else x) for a, x in v.items()}
            if callable(v):
                events[k[3:] if k.startswith("on_") else k] = v
                wire[k] = True
            else:
                wire[k] = v
        return wire, events

    def _set_handlers(self, f: Fiber, events: Dict[str, Callable[..., Any]]) -> None:
        for ev in f.events - set(events):
            self.handlers.pop((f.id, ev), None)
        for ev, fn in events.items():
            self.handlers[(f.id, ev)] = fn
        f.events = set(events)

    def _mount(self, e: Element, parent: Fiber) -> Fiber:
        if isinstance(e.type, str):
            f = Fiber("host", e, parent, self)
            f.id = self._next_id
            self._next_id += 1
            wire, events = self._wire(e.props)
            f.sent = wire
            self.ops.append(Create(f.id, e.type, dict(wire)))
            self._set_handlers(f, events)
            self._reconcile_children(f, e.children)
            self._sync(f)
        else:
            f = Fiber("comp", e, parent, self)
            self._render_comp(f)
        return f

    def _update(self, f: Fiber, e: Element) -> None:
        f.element = e
        if f.kind == "host":
            wire, events = self._wire(e.props)
            changed = {k: v for k, v in wire.items() if k not in f.sent or not _same(f.sent[k], v)}
            removed = [k for k in f.sent if k not in wire]
            if changed or removed:
                self.ops.append(Update(f.id, changed, removed))
            f.sent = wire
            self._set_handlers(f, events)
            self._reconcile_children(f, e.children)
            self._sync(f)
        else:
            self._render_comp(f)

    def _render_comp(self, f: Fiber) -> None:
        e = f.element
        out = render_with_hooks(f, e.type.fn, e.children, e.props)
        self._reconcile_children(f, flatten([out]))

    def _reconcile_children(self, parent: Fiber, elements: List[Element]) -> None:
        old = parent.children
        old_keyed = {o.key: o for o in old if o.key is not None}
        used: Set[int] = set()
        new: List[Fiber] = []
        for i, e in enumerate(elements):
            cand = None
            if e.key is not None:
                c = old_keyed.get(e.key)
                if c is not None and c.element.type == e.type:
                    cand = c
            elif i < len(old) and old[i].key is None and old[i].element.type == e.type:
                cand = old[i]
            if cand is not None and id(cand) not in used:
                used.add(id(cand))
                self._update(cand, e)
            else:
                cand = self._mount(e, parent)
            new.append(cand)
        for o in old:
            if id(o) not in used:
                self._unmount(o)
        parent.children = new

    def _unmount(self, f: Fiber) -> None:
        for c in f.children:
            self._unmount(c)
        f.unmounted = True
        for kind, data in f.hooks:
            if kind == "effect" and data.cleanup:
                cleanup, data.cleanup = data.cleanup, None
                cleanup()
        if f.kind == "host":
            for ev in f.events:
                self.handlers.pop((f.id, ev), None)
            self._deletes.append(f.id)

    def _sync(self, host: Fiber) -> None:
        """Make host.native match the desired host-children order using remove/insert ops."""
        want = [c.id for c in _host_children(host)]
        wanted = set(want)
        native = host.native
        for nid in [n for n in native if n not in wanted]:
            self.ops.append(Remove(host.id, nid))
            native.remove(nid)
        for i, nid in enumerate(want):
            if i < len(native) and native[i] == nid:
                continue
            if nid in native:
                self.ops.append(Remove(host.id, nid))
                native.remove(nid)
            self.ops.append(Insert(host.id, nid, i))
            native.insert(i, nid)
