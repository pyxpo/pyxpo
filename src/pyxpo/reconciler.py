from __future__ import annotations

import asyncio
import inspect
import warnings
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from . import responsive as _resp
from .animated import runtime as _anim
from .element import Element, flatten
from .apis import _env as _env_mod
from .hooks import _same, render_with_hooks
from .style import normalize_shared as normalize_style
from .ops import Create, Delete, Insert, Op, Remove, Update

_MISSING = object()
# prop value types that go to the wire as is: never callable, never an animated event
_PLAIN_PROP_TYPES = frozenset((str, int, float, bool, type(None), dict, list, tuple))


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
        self.ctx_below = False  # this fiber or a descendant reads context: memo must not skip it


def _host_ids(fiber: Fiber, out: List[int]) -> List[int]:
    """Append the native ids of fiber's nearest host descendants (components are transparent), in order."""
    for c in fiber.children:
        if c.kind == "comp":
            _host_ids(c, out)
        else:
            out.append(c.id)
    return out


def _stable(want: List[int], old_pos: Dict[int, int]) -> Set[int]:
    """Ids of `want` that form a longest run whose old positions increase: these need no move (patience sort)."""
    seq = [(old_pos[n], n) for n in want if n in old_pos]
    tails: List[int] = []  # tails[k] = index in seq of the smallest tail of an increasing run of length k + 1
    prev = [-1] * len(seq)
    for i, (pos, _) in enumerate(seq):
        lo, hi = 0, len(tails)
        while lo < hi:
            mid = (lo + hi) // 2
            if seq[tails[mid]][0] < pos:
                lo = mid + 1
            else:
                hi = mid
        if lo:
            prev[i] = tails[lo - 1]
        if lo == len(tails):
            tails.append(i)
        else:
            tails[lo] = i
    out: Set[int] = set()
    i = tails[-1] if tails else -1
    while i >= 0:
        out.add(seq[i][1])
        i = prev[i]
    return out


def _neg_depth(p: Tuple[Fiber, Any, Any]) -> int:
    return -p[0].depth


_ARITY: Dict[Any, bool] = {}


def _takes_value(fn: Callable[..., Any]) -> bool:
    """True when `fn` can be called with one positional argument. Cached per code object."""
    code = getattr(fn, "__code__", None)
    # decorated wrappers share one code object but signature() follows __wrapped__/__signature__: don't cache
    if code is not None and (hasattr(fn, "__wrapped__") or hasattr(fn, "__signature__")):
        code = None
    key = (code, getattr(fn, "__self__", None) is not None) if code is not None else None
    if key is not None and key in _ARITY:
        return _ARITY[key]
    try:
        inspect.signature(fn).bind(None)
        ok = True
    except TypeError:
        ok = False
    except ValueError:
        ok = False
    if key is not None:
        _ARITY[key] = ok
    return ok


class Reconciler:
    """Diffs element trees into a flat list of native ops. One commit = one ops list."""

    def __init__(self, schedule: Optional[Callable[[Fiber], None]] = None) -> None:
        self._schedule = schedule
        self.loop: Any = None
        self.env = _env_mod.Env()
        self.ops: List[Op] = []
        self.pending_effects: List[Tuple[Fiber, Any, Callable[[], Any]]] = []
        self.handlers: Dict[Tuple[int, str], Callable[..., Any]] = {}
        self._deletes: List[int] = []
        self._next_id = 2
        self.id_counter = 0  # use_id
        # Effect, cleanup and async-effect errors go here (App sets it). None: the first one is re-raised at the end
        # of run_effects, after every other effect has run.
        self.on_error: Optional[Callable[[BaseException], Any]] = None
        self._error: Optional[BaseException] = None
        self.root = Fiber("root", None, None, self)
        self.root.id = 1
        # host fibers whose style holds a breakpoint map: id -> (fiber, breakpoint it was resolved at)
        self.responsive: Dict[int, Tuple[Fiber, str]] = {}
        self._bp_key: Tuple[Any, int] = (None, -1)
        self._bp_name = ""
        self._refreshed_bp: Optional[str] = None

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
        marks = (len(self.ops), len(self.pending_effects), len(self._deletes), self._next_id, _anim.mark())
        try:
            self._render_comp(fiber)
        except Exception as e:  # noqa: BLE001
            fiber = self._catch(fiber.parent, marks, e)  # the boundary that now shows its fallback (or re-raise)
        host = fiber.parent
        while host.kind == "comp":
            host = host.parent
        self._sync(host)

    def take_ops(self) -> List[Op]:
        ops = _anim.drain()
        ops.extend(self.ops)
        ops.extend([Delete(i) for i in self._deletes])
        self.ops, self._deletes = [], []
        return ops

    def run_effects(self) -> None:
        pending = self.pending_effects
        if pending:
            self.pending_effects = []
            live = [p for p in pending if not p[0].unmounted]
            if len(live) > 1:
                live.sort(key=_neg_depth)  # children before parents (stable: a fiber keeps its hook order)
            for _, cell, _fn in live:
                if cell.cleanup is not None:
                    cleanup, cell.cleanup = cell.cleanup, None
                    try:
                        cleanup()
                    except Exception as e:  # noqa: BLE001
                        self._report(e)
            for _, cell, fn in live:
                try:
                    result = fn()
                except Exception as e:  # noqa: BLE001
                    self._report(e)
                    continue
                if result is None:
                    continue
                if callable(result):
                    cell.cleanup = result
                elif inspect.isawaitable(result):
                    self._run_async_effect(result)
        if self._error is not None:
            err, self._error = self._error, None
            raise err

    def _report(self, e: BaseException) -> None:
        if self.on_error is not None:
            self.on_error(e)
        elif self._error is None:
            self._error = e

    def _run_async_effect(self, aw: Any) -> None:
        warnings.warn("async effect: it runs as a task and cannot return a cleanup; use use_async for that",
                      RuntimeWarning, stacklevel=3)
        self._spawn(aw, "async effect")

    def _spawn(self, aw: Any, what: str) -> None:
        loop = self.loop
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
        if loop is None:
            if inspect.iscoroutine(aw):
                aw.close()
            self._report(RuntimeError("%s needs an app running on an asyncio loop" % what))
            return

        async def run() -> None:
            await aw

        def done(t: Any) -> None:
            if not t.cancelled() and t.exception() is not None:
                self._report(t.exception())
                if self._error is not None:  # no app: let the loop's exception handler log it
                    err, self._error = self._error, None
                    raise err

        loop.create_task(run()).add_done_callback(done)

    def dispatch(self, node_id: int, event: str, payload: Optional[Dict[str, Any]] = None) -> bool:
        fn = self.handlers.get((node_id, event))
        if fn is None:
            return False
        if payload and _takes_value(fn):
            result = fn(payload.get("value"))
        else:
            result = fn()
        if inspect.isawaitable(result):  # `async def` handler: run it as a task on the app loop
            self._spawn(result, "async event handler")
        return True

    def breakpoint(self) -> str:
        """Active responsive breakpoint for the current window width."""
        key = (self.env._data["window"]["width"], _resp.version())
        if key != self._bp_key:
            self._bp_key = key
            self._bp_name = _resp.breakpoint_for(key[0] or 0)
        return self._bp_name

    def refresh_responsive(self) -> bool:
        """After the window crossed a breakpoint: re-style the views whose style holds a breakpoint map, without
        re-rendering any component. Returns True when it queued ops."""
        bp = self.breakpoint()
        if bp == self._refreshed_bp:
            return False
        self._refreshed_bp = bp
        queued = False
        for fid, (f, used) in list(self.responsive.items()):
            if used == bp:
                continue
            if f.unmounted or f.element is None:
                del self.responsive[fid]
                continue
            style, _ = _resp.resolve_style(f.element.props.get("style"), bp)
            new = normalize_style(style)
            self.responsive[fid] = (f, bp)
            old = f.sent.get("style", _MISSING)
            if old is _MISSING or not _same(old, new):
                self.ops.append(Update(f.id, {"style": new}, []))
                f.sent = dict(f.sent, style=new)
                queued = True
        return queued

    # -- internals -----------------------------------------------------
    def _wire(self, props: Dict[str, Any], f: Optional[Fiber] = None):
        wire: Dict[str, Any] = {}
        events: Dict[str, Callable[..., Any]] = {}
        for k, v in props.items():
            if k == "ref":
                continue
            if k == "style":
                if v is not None:
                    bp = self.breakpoint()
                    v, used = _resp.resolve_style(v, bp)
                    if f is not None:
                        if used:
                            self.responsive[f.id] = (f, bp)
                        elif self.responsive:
                            self.responsive.pop(f.id, None)
                wire[k] = normalize_style(v)
                continue
            if v.__class__ in _PLAIN_PROP_TYPES:
                wire[k] = v
                continue
            if getattr(v, "_is_animated_event", False):
                if v.native:
                    wire[k] = v._wire()
                    if v.listener is not None:
                        events[k[3:]] = v.listener
                    continue
            if callable(v):
                events[k[3:] if k.startswith("on_") else k] = v
                wire[k] = True
            else:
                wire[k] = v
        return wire, events

    def _set_handlers(self, f: Fiber, events: Dict[str, Callable[..., Any]]) -> None:
        handlers = self.handlers
        fid = f.id
        if f.events == events.keys():
            for ev, fn in events.items():
                handlers[(fid, ev)] = fn
            return
        for ev in f.events:
            if ev not in events:
                handlers.pop((fid, ev), None)
        for ev, fn in events.items():
            handlers[(fid, ev)] = fn
        f.events = set(events)

    def _mount(self, e: Element, parent: Fiber) -> Fiber:
        if isinstance(e.type, str):
            f = Fiber("host", e, parent, self)
            f.id = self._next_id
            self._next_id += 1
            wire, events = self._wire(e.props, f)
            f.sent = wire
            self._bind_ref(f, e)
            self.ops.append(Create(f.id, e.type, wire))  # wire is never mutated after this (f.sent is replaced)
            self._set_handlers(f, events)
            if e.children:
                try:
                    self._reconcile_children(f, e.children)
                except BaseException:
                    self._unmount(f)  # never attached: release its ref and handlers, stop its setters
                    raise
                self._sync(f)
        else:
            f = Fiber("comp", e, parent, self)
            try:
                self._render_comp(f)
            except BaseException:
                self._unmount(f)
                raise
        return f

    def _update(self, f: Fiber, e: Element) -> None:
        old = f.element
        if f.kind == "host":
            f.element = e
            ref = e.props.get("ref")
            old_ref = old.props.get("ref") if old is not None else None
            if old_ref is not None and old_ref is not ref and hasattr(old_ref, "_unbind"):
                old_ref._unbind(f.id)  # ref prop swapped or removed: the old ref must not keep this view
            wire, events = self._wire(e.props, f)
            if ref is not None and hasattr(ref, "_bind"):
                ref._bind(f.id, e.type)
            sent = f.sent
            changed = {}
            for k, v in wire.items():
                o = sent.get(k, _MISSING)
                if o is not v and (o is _MISSING or not _same(o, v)):
                    changed[k] = v
            removed = [] if sent.keys() == wire.keys() else [k for k in sent if k not in wire]
            if changed or removed:
                self.ops.append(Update(f.id, changed, removed))
            f.sent = wire
            self._set_handlers(f, events)
            if e.children or f.children:  # leaf stays a leaf: nothing to reconcile or reorder
                self._reconcile_children(f, e.children)
                self._sync(f)
        elif e.type.memo is not None and not f.ctx_below and e.type.memo(old, e):
            f.element = e  # memo hit: props unchanged, keep the rendered subtree as is
        else:
            f.element = e
            self._render_comp(f)

    @staticmethod
    def _bind_ref(f: Fiber, e: Element) -> None:
        ref = e.props.get("ref")
        if ref is not None and hasattr(ref, "_bind"):
            ref._bind(f.id, e.type)

    def _render_comp(self, f: Fiber) -> None:
        e = f.element
        if e.type._boundary:
            self._render_boundary(f)
            return
        out = render_with_hooks(f, e.type.fn, e.children, e.props)
        self._reconcile_children(f, [out] if out.__class__ is Element else flatten([out]))

    # -- error boundaries ------------------------------------------------
    def _render_boundary(self, f: Fiber) -> None:
        """Render an ErrorBoundary. A render error below it rolls its subtree back and shows the fallback. An error
        while the fallback is shown propagates to the next boundary up."""
        marks = (len(self.ops), len(self.pending_effects), len(self._deletes), self._next_id, _anim.mark())
        e = f.element
        try:
            out = render_with_hooks(f, e.type.fn, e.children, e.props)
            cell = f.hooks[0][1]
            if cell.showing != (cell.error is not None):  # switched between children and fallback: remount
                self._unmount_children(f)
                cell.showing = cell.error is not None
            self._reconcile_children(f, [out] if out.__class__ is Element else flatten([out]))
        except Exception as err:  # noqa: BLE001
            if not f.hooks_ready or f.hooks[0][1].error is not None:
                raise
            self._fallback(f, marks, err)

    def _catch(self, node: Optional[Fiber], marks: Tuple[Any, ...], err: Exception) -> Fiber:
        """Hand `err` to the innermost boundary at or above `node` that is not showing its fallback. Returns it."""
        while True:
            b = node
            while b is not None and not (b.kind == "comp" and b.element.type._boundary and b.hooks_ready
                                         and b.hooks[0][1].error is None):
                b = b.parent
            if b is None:
                raise err
            try:
                self._fallback(b, marks, err)
                return b
            except Exception as e2:  # noqa: BLE001  # the fallback itself failed: next boundary up
                err, node = e2, b.parent

    def _fallback(self, b: Fiber, marks: Tuple[Any, ...], err: Exception) -> None:
        """Roll back everything emitted since `marks` (all of it lies inside b), unmount b's children, render the
        fallback. Fibers created since the marks were never sent: their Delete ops and handlers are dropped."""
        n_ops, n_eff, n_del, id_mark, anim_mark = marks
        del self.ops[n_ops:]
        del self.pending_effects[n_eff:]
        _anim.rollback(anim_mark)  # before the unmount below: its cleanups may queue deletes of older nodes
        self._unmount_children(b)
        self._deletes[n_del:] = [i for i in self._deletes[n_del:] if i < id_mark]
        if self._next_id > id_mark:
            for k in [k for k in self.handlers if k[0] >= id_mark]:
                del self.handlers[k]
        cell = b.hooks[0][1]
        cell.error = err
        cell.showing = True
        on_error = b.element.props.get("on_error")
        if on_error is not None:
            try:
                on_error(err)
            except Exception as e:  # noqa: BLE001
                self._report(e)
        e = b.element
        out = render_with_hooks(b, e.type.fn, e.children, e.props)
        self._reconcile_children(b, [out] if out.__class__ is Element else flatten([out]))

    def _unmount_children(self, f: Fiber) -> None:
        children, f.children = f.children, []
        for c in children:
            self._unmount(c)

    def _reconcile_children(self, parent: Fiber, elements: List[Element]) -> None:
        old = parent.children
        mount = self._mount
        if not old:
            new: List[Fiber] = []
            try:
                for e in elements:
                    new.append(mount(e, parent))
            except BaseException:
                for c in new:  # mounted but never attached to parent: nothing else will unmount them
                    self._unmount(c)
                raise
            parent.children = new
            return
        n_old = len(old)
        if n_old == 1 and len(elements) == 1:  # single child (most component renders): no key map needed
            o, e = old[0], elements[0]
            if o.key == e.key and o.element.type == e.type:
                self._update(o, e)
                return
        old_keyed = {o.key: o for o in old if o.key is not None}
        used: Set[Fiber] = set()  # Fiber hashes by identity
        new = []
        update = self._update
        try:
            for i, e in enumerate(elements):
                k = e.key
                if k is not None:
                    cand = old_keyed.get(k)
                    if cand is not None and cand.element.type != e.type:
                        cand = None
                elif i < n_old:
                    cand = old[i]
                    if cand.key is not None or cand.element.type != e.type:
                        cand = None
                else:
                    cand = None
                if cand is not None and cand not in used:
                    used.add(cand)
                    update(cand, e)
                else:
                    cand = mount(e, parent)
                new.append(cand)
        except BaseException:
            for c in new:
                if c not in used:  # freshly mounted, never attached (old ones stay in parent.children)
                    self._unmount(c)
            raise
        if len(used) != n_old:
            for o in old:
                if o not in used:
                    self._unmount(o)
        parent.children = new

    def _unmount(self, f: Fiber) -> None:
        if f.unmounted:
            return
        for c in f.children:
            self._unmount(c)
        f.unmounted = True
        for kind, data in f.hooks:
            if kind == "effect" and data.cleanup:
                cleanup, data.cleanup = data.cleanup, None
                try:
                    cleanup()
                except Exception as e:  # noqa: BLE001  # never leave a commit half-unmounted
                    self._report(e)
        if f.kind == "host":
            ref = f.element.props.get("ref") if f.element is not None else None
            if ref is not None and hasattr(ref, "_unbind"):
                ref._unbind(f.id)
            for ev in f.events:
                self.handlers.pop((f.id, ev), None)
            self.responsive.pop(f.id, None)
            self._deletes.append(f.id)

    def _sync(self, host: Fiber) -> None:
        """Make host.native match the desired host-children order with the fewest moves.

        Children that keep their relative order (the longest increasing run of their old positions) stay put; every
        other kept child moves once and every new child is inserted once. Going right to left, each one lands just
        before its already placed right neighbour, so the result is exact whatever order the moves happen in."""
        want = _host_ids(host, [])
        native = host.native
        if native == want:
            return
        wanted = set(want)
        if len(wanted) != len(native) or any(n not in wanted for n in native):
            for nid in [n for n in native if n not in wanted]:
                self.ops.append(Remove(host.id, nid))
            native[:] = [n for n in native if n in wanted]
        if not native:  # first mount or full replace: plain appends
            for i, nid in enumerate(want):
                self.ops.append(Insert(host.id, nid, i))
            native[:] = want
            return
        old_pos = {nid: i for i, nid in enumerate(native)}
        stay = _stable(want, old_pos)
        nxt: Optional[int] = None
        for nid in reversed(want):
            if nid not in stay:
                if nid in old_pos:
                    self.ops.append(Remove(host.id, nid))
                    native.remove(nid)
                i = native.index(nxt) if nxt is not None else len(native)
                self.ops.append(Insert(host.id, nid, i))
                native.insert(i, nid)
            nxt = nid
