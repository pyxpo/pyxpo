"""Glue between animated nodes/animations and the running App: op queue, id counters, event routing."""
from __future__ import annotations

import weakref
from typing import Any, Callable, Dict, List, Optional

from . import engine
from ..ops import AListen, ANode, ANodeDel, ASet, Op

_app: Any = None
_queue: List[Op] = []
_node_id = 0
_anim_id = 0
_drains = 0  # bumped whenever the queue is emptied: a rollback mark from before that is void
nodes: "weakref.WeakValueDictionary[int, Any]" = weakref.WeakValueDictionary()
callbacks: Dict[int, Callable[[Dict[str, Any]], None]] = {}
NOAPP = object()


_token: Any = NOAPP


def set_app(app: Any) -> None:
    global _app, _drains, _token
    _app = app
    _token = object() if app is not None else NOAPP
    _drains += 1
    _queue.clear()
    callbacks.clear()


def native_reset() -> None:
    """The native side lost its node graph (new activity): every node registers again when next wired."""
    global _drains, _token
    _token = object() if _app is not None else NOAPP
    _drains += 1
    _queue.clear()
    callbacks.clear()


def token() -> Any:
    return _token


def next_node_id() -> int:
    global _node_id
    _node_id += 1
    return _node_id


def next_anim_id() -> int:
    global _anim_id
    _anim_id += 1
    return _anim_id


def queue(op: Op) -> None:
    _queue.append(op)


def drain() -> List[Op]:
    """Pending node ops. The reconciler sends them ahead of Create/Update so bindings never dangle."""
    global _drains
    out = list(_queue)
    _queue.clear()
    _drains += 1
    return out


def mark() -> Any:
    return len(_queue), _drains


def rollback(m: Any) -> None:
    """Drop node registrations queued since `mark()` (a render that an ErrorBoundary rolled back): the views that
    used them were never sent, and the effects that would free them never run. A dropped node registers again the
    next time it is wired. Deletes of older nodes (cleanups of really unmounted fibers) are kept."""
    n, d = m
    if d != _drains or len(_queue) <= n:
        return  # nothing queued, or it was already sent
    tail = _queue[n:]
    dropped = {op.id for op in tail if op.__class__ is ANode}
    if not dropped:
        return
    del _queue[n:]
    _queue.extend(op for op in tail if not (op.__class__ in (ANode, AListen, ANodeDel) and op.id in dropped))
    for i in dropped:
        node = nodes.get(i)
        if node is not None:
            node._token = None


def send(*ops: Op) -> None:
    """Send now (with any queued node ops first)."""
    if _app is None:
        return
    _app._send(drain() + list(ops))


def delete_node(node: Any) -> None:
    if node._token is token():
        node._token = None
        queue(ANodeDel(node.id))


def handle_event(msg: Dict[str, Any]) -> None:
    ev, pl = msg["event"], msg.get("payload") or {}
    if ev == "anim_value":
        for k, v in pl.items():
            n = nodes.get(int(k))
            if n is not None and hasattr(n, "_update"):
                n._update(float(v))
        return
    for k, v in (pl.get("values") or {}).items():
        n = nodes.get(int(k))
        if n is not None and hasattr(n, "_sync"):
            n._sync(float(v))
    cb = callbacks.pop(msg["id"], None)
    if cb is not None:
        cb({"finished": bool(pl.get("finished"))})


# -- Python-driven fallback (use_native_driver=False, callable easings, desktop) -------------------
py = engine.Driver()
_pump_scheduled = False
_clock: Optional[Callable[[], float]] = None   # tests replace this; ms


def _now() -> float:
    if _clock is not None:
        return _clock()
    import time
    return time.monotonic() * 1000.0


def py_start(aid: int, spec: Dict[str, Any], values: List[Any]) -> None:
    for v in values:
        if v.id not in py.nodes:
            py.anode(v.id, {"t": "value", "v": v._value})
        else:
            py.values[v.id] = v._value
    py_events(py.animate(aid, spec))
    _schedule_pump()


def py_aset(nid: int, v: float) -> None:
    if nid in py.nodes:
        py_events(py.aset({nid: v}))


def py_stop(aid: int) -> None:
    py_events(py.astop(aid))


def py_tick(now: Optional[float] = None) -> None:
    evs = py.tick(_now() if now is None else now)
    touched = [n for n in py.touched if n in py.values]
    if touched:
        for n in touched:
            node = nodes.get(n)
            if node is not None:
                node._value = py.values[n]
        send(ASet({str(n): py.values[n] for n in touched}))
    py_events(evs)


def py_events(evs: List[Dict[str, Any]]) -> None:
    for e in evs:
        if e["event"] == "anim_end":
            for k, v in e["payload"]["values"].items():
                node = nodes.get(int(k))
                if node is not None:
                    node._value = v
        handle_event(e)


def _schedule_pump() -> None:
    global _pump_scheduled
    loop = getattr(_app, "loop", None)
    if _pump_scheduled or loop is None:
        return
    _pump_scheduled = True

    def pump() -> None:
        global _pump_scheduled
        _pump_scheduled = False
        try:
            py_tick()
        except Exception as e:  # noqa: BLE001
            _app.on_error(e)
            return
        _app._request_flush()
        if py.active:
            _schedule_pump()

    loop.call_later(1 / 60, pump)
