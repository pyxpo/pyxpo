from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable, List, NamedTuple, Optional, Sequence

from .component import Component


class HookError(RuntimeError):
    pass


_stack: List[Any] = []


def render_with_hooks(fiber: Any, fn: Callable[..., Any], args: Sequence[Any], kwargs: dict) -> Any:
    fiber.hook_index = 0
    _stack.append(fiber)
    try:
        out = fn(*args, **kwargs)
    finally:
        _stack.pop()
    if fiber.hooks_ready and fiber.hook_index != len(fiber.hooks):
        raise HookError("rendered fewer hooks than previous render (hooks must not be conditional)")
    fiber.hooks_ready = True
    return out


def _current(name: str) -> Any:
    if not _stack:
        raise HookError("%s() called outside of a component render" % name)
    return _stack[-1]


def _use(kind: str, init: Callable[[Any], Any]):
    f = _current(kind)
    i = f.hook_index
    f.hook_index += 1
    if f.hooks_ready:
        if i >= len(f.hooks):
            raise HookError("rendered more hooks than previous render (%s)" % kind)
        if f.hooks[i][0] != kind:
            raise HookError("hook order changed: expected %s, got %s" % (f.hooks[i][0], kind))
        return f.hooks[i][1], False
    data = init(f)
    f.hooks.append((kind, data))
    return data, True


def _same(a: Any, b: Any) -> bool:
    if a is b:
        return True
    if type(a) is not type(b):
        return False
    try:
        return bool(a == b)
    except Exception:
        return False


def _deps_changed(old: Optional[list], new: Optional[Sequence[Any]]) -> bool:
    if old is None or new is None or len(old) != len(new):
        return True
    return any(not _same(a, b) for a, b in zip(old, new))


class _State:
    __slots__ = ("value", "setter")


def use_state(initial: Any = None):
    def init(f: Any) -> _State:
        cell = _State()
        cell.value = initial() if callable(initial) else initial

        def set_state(v: Any) -> None:
            new = v(cell.value) if callable(v) else v
            if f.unmounted or _same(new, cell.value):
                return
            cell.value = new
            f.rec.schedule(f)

        cell.setter = set_state
        return cell

    cell, _ = _use("state", init)
    return cell.value, cell.setter


class Ref:
    def __init__(self, current: Any = None) -> None:
        self.current = current


def use_ref(initial: Any = None) -> Ref:
    ref, _ = _use("ref", lambda f: Ref(initial))
    return ref


class _Memo:
    __slots__ = ("deps", "value")


def use_memo(factory: Callable[[], Any], deps: Optional[Sequence[Any]] = None) -> Any:
    cell, new = _use("memo", lambda f: _Memo())
    if new or _deps_changed(cell.deps, deps):
        cell.value = factory()
        cell.deps = None if deps is None else list(deps)
    return cell.value


def use_callback(fn: Callable[..., Any], deps: Optional[Sequence[Any]] = None) -> Callable[..., Any]:
    return use_memo(lambda: fn, deps)


class _Effect:
    __slots__ = ("deps", "cleanup")

    def __init__(self) -> None:
        self.deps = None
        self.cleanup = None


def use_effect(fn: Callable[[], Any], deps: Optional[Sequence[Any]] = None) -> None:
    """Run fn after commit. deps=None: every render. deps=[]: once. fn may return a cleanup callable."""
    f = _current("use_effect")
    cell, new = _use("effect", lambda _f: _Effect())
    if new or _deps_changed(cell.deps, deps):
        cell.deps = None if deps is None else list(deps)
        f.rec.pending_effects.append((f, cell, fn))


class Context:
    def __init__(self, default: Any) -> None:
        self.default = default
        self.Provider = Component(lambda *children, value=None: list(children), name="Provider")


def create_context(default: Any = None) -> Context:
    return Context(default)


def use_context(ctx: Context) -> Any:
    cur = _current("use_context")
    cur.ctx_below = True
    node = cur.parent
    while node is not None:
        if node.element is not None and node.element.type is ctx.Provider:
            return node.element.props.get("value")
        node.ctx_below = True  # a memoized ancestor must re-render when a Provider above changes
        node = node.parent
    return ctx.default


class AsyncResult(NamedTuple):
    loading: bool
    value: Any
    error: Optional[BaseException]


def use_async(fn: Callable[[], Any], deps: Optional[Sequence[Any]] = None) -> AsyncResult:
    """Run fn (coroutine fn, or blocking fn in a worker thread) when deps change. Returns (loading, value, error)."""
    rec = _current("use_async").rec
    state, set_state = use_state(lambda: AsyncResult(True, None, None))

    def run() -> Callable[[], None]:
        if rec.loop is None:
            raise RuntimeError("use_async needs an app running on an asyncio loop")
        token = {"cancelled": False}
        set_state(AsyncResult(True, None, None))

        async def job() -> None:
            try:
                if inspect.iscoroutinefunction(fn):
                    value = await fn()
                else:
                    value = await asyncio.to_thread(fn)
                res = AsyncResult(False, value, None)
            except Exception as e:  # noqa: BLE001
                res = AsyncResult(False, None, e)
            if not token["cancelled"]:
                set_state(res)

        task = rec.loop.create_task(job())

        def cleanup() -> None:
            token["cancelled"] = True
            task.cancel()

        return cleanup

    use_effect(run, [] if deps is None else deps)
    return state


def reset_deps(fiber: Any) -> None:
    """Hot reload: force memos to recompute and effects to clean up and re-run on the next render."""
    for kind, data in fiber.hooks:
        if kind in ("memo", "effect"):
            data.deps = None
