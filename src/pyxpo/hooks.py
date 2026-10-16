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
    except BaseException:
        if not fiber.hooks_ready:
            del fiber.hooks[:]  # a failed first render must not leave a partial hook list behind
        raise
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
    f = _stack[-1] if _stack else _current(kind)
    i = f.hook_index
    f.hook_index = i + 1
    if f.hooks_ready:
        hooks = f.hooks
        if i >= len(hooks):
            raise HookError("rendered more hooks than previous render (%s)" % kind)
        k, data = hooks[i]
        if k != kind:
            raise HookError("hook order changed: expected %s, got %s" % (k, kind))
        return data, False
    data = init(f)
    f.hooks.append((kind, data))
    return data, True


def _same(a: Any, b: Any) -> bool:
    if a is b:
        return True
    if type(a) is not type(b):
        return False
    try:
        if a == b:
            return True
    except Exception:
        return False
    return a.__class__ is float and a != a and b != b  # NaN is the same as NaN (like Object.is)


def _check_deps(name: str, deps: Any) -> None:
    if deps is not None and deps.__class__ is not list and deps.__class__ is not tuple \
            and not isinstance(deps, (list, tuple)):
        raise HookError("%s deps must be a list, a tuple or None, got %s" % (name, type(deps).__name__))


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
    """`useRef` cell. Put on a host element (`ref=r`) and `r.current` becomes that view's handle
    (`scrollTo`, `focus`, ...) while it is mounted."""

    def __init__(self, current: Any = None) -> None:
        self.current = current

    def _bind(self, node_id: int, host: Any = None) -> None:
        from .components._handles import make_handle
        cur = self.current
        if getattr(cur, "_id", None) != node_id:
            self.current = make_handle(host, node_id)

    def _unbind(self, node_id: int) -> None:
        if getattr(self.current, "_id", None) == node_id:
            self.current = None


def use_ref(initial: Any = None) -> Ref:
    ref, _ = _use("ref", lambda f: Ref(initial))
    return ref


class _Memo:
    __slots__ = ("deps", "value")


def use_memo(factory: Callable[[], Any], deps: Optional[Sequence[Any]] = None) -> Any:
    _check_deps("use_memo", deps)
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


def _effect(name: str, fn: Callable[[], Any], deps: Optional[Sequence[Any]]) -> None:
    f = _current(name)
    _check_deps(name, deps)
    cell, new = _use("effect", lambda _f: _Effect())
    if new or _deps_changed(cell.deps, deps):
        cell.deps = None if deps is None else list(deps)
        f.rec.pending_effects.append((f, cell, fn))


def use_effect(fn: Callable[[], Any], deps: Optional[Sequence[Any]] = None) -> None:
    """Run fn after commit. deps=None: every render. deps=[]: once. fn may return a cleanup callable.

    Child effects run before parent effects, and all cleanups of a commit run before its setups. An exception in
    one effect or cleanup goes to `App.on_error` and does not stop the others. An `async def` effect is scheduled
    as a task on the app loop; it cannot return a cleanup (use `use_async` for that)."""
    _effect("use_effect", fn, deps)


def use_layout_effect(fn: Callable[[], Any], deps: Optional[Sequence[Any]] = None) -> None:
    """Same timing as `use_effect`: native layout is measured asynchronously, so there is no earlier point to run."""
    _effect("use_layout_effect", fn, deps)


class Context:
    def __init__(self, default: Any) -> None:
        self.default = default
        self.Provider = Component(lambda *children, value=None: list(children), name="Provider")
        self.Consumer = Component(lambda children=None: children(use_context(self)) if children else None, name="Consumer")


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
    """Hot reload: force memos to recompute and effects to clean up and re-run on the next render.
    Error boundaries retry their children (the edit may have fixed the error)."""
    for kind, data in fiber.hooks:
        if kind in ("memo", "effect"):
            data.deps = None
        elif kind == "boundary":
            data.error = None


class _Reducer:
    __slots__ = ("value", "reducer", "dispatch")


def use_reducer(reducer: Callable[[Any, Any], Any], initial_arg: Any, init: Optional[Callable[[Any], Any]] = None):
    """`state, dispatch = use_reducer(reducer, initial_arg, init=None)`. dispatch is stable; a reducer result that is
    the same as the current state does not re-render."""
    def make(f: Any) -> _Reducer:
        cell = _Reducer()
        cell.value = init(initial_arg) if init is not None else initial_arg

        def dispatch(action: Any) -> None:
            if f.unmounted:
                return
            new = cell.reducer(cell.value, action)
            if _same(new, cell.value):
                return
            cell.value = new
            f.rec.schedule(f)

        cell.dispatch = dispatch
        return cell

    cell, _ = _use("reducer", make)
    cell.reducer = reducer  # dispatch uses the reducer of the latest render
    return cell.value, cell.dispatch


def use_id() -> str:
    """A string id that is stable for the life of the component and unique within the app."""
    def make(f: Any) -> str:
        rec = f.rec
        rec.id_counter += 1
        return ":p%d:" % rec.id_counter

    value, _ = _use("id", make)
    return value


def use_imperative_handle(ref: Any, create: Callable[[], Any], deps: Optional[Sequence[Any]] = None) -> None:
    """Expose `create()` on a parent's ref (`ref.current`, or a callable ref). Cleared on unmount."""
    _check_deps("use_imperative_handle", deps)

    def setup() -> Optional[Callable[[], None]]:
        if ref is None:
            return None
        if callable(ref) and not hasattr(ref, "current"):
            ref(create())
            return lambda: ref(None)
        ref.current = create()

        def clear() -> None:
            ref.current = None

        return clear

    _effect("use_imperative_handle", setup, None if deps is None else [ref] + list(deps))


class _Store:
    __slots__ = ("value", "get")


def use_sync_external_store(subscribe: Callable[[Callable[[], None]], Any], get_snapshot: Callable[[], Any],
                            get_server_snapshot: Optional[Callable[[], Any]] = None) -> Any:
    """Read an external store. `subscribe(on_change)` returns an unsubscribe callable; `get_snapshot()` returns the
    current value (it must return the same object while the store is unchanged)."""
    f = _current("use_sync_external_store")
    snap = get_snapshot()
    cell, _ = _use("store", lambda _f: _Store())
    cell.value = snap
    cell.get = get_snapshot

    def check() -> None:
        if not f.unmounted and not _same(cell.get(), cell.value):
            f.rec.schedule(f)

    def sub() -> Optional[Callable[[], Any]]:
        unsubscribe = subscribe(check)
        check()  # the store may have changed between render and subscribe
        return unsubscribe if callable(unsubscribe) else None

    _effect("use_sync_external_store", sub, [subscribe])
    return snap


def _start_transition(fn: Callable[[], Any]) -> None:
    fn()


def use_transition():
    """`(is_pending, start_transition)`. pyxpo renders synchronously, so is_pending is always False."""
    return False, _start_transition


def use_deferred_value(value: Any, initial_value: Any = None) -> Any:
    """pyxpo has no concurrent rendering: the value is returned as is."""
    return value


def use_debug_value(value: Any, format: Optional[Callable[[Any], Any]] = None) -> None:
    """No-op (React DevTools label)."""
    return None


# React Native spellings (same objects)
useState = use_state
useEffect = use_effect
useLayoutEffect = use_layout_effect
useRef = use_ref
useMemo = use_memo
useCallback = use_callback
useContext = use_context
createContext = create_context
useReducer = use_reducer
useId = use_id
useImperativeHandle = use_imperative_handle
useSyncExternalStore = use_sync_external_store
useTransition = use_transition
useDeferredValue = use_deferred_value
useDebugValue = use_debug_value
useAsync = use_async


# -- environment hooks (window size, color scheme, insets, keyboard) ---------
def _use_env(select: Callable[[Any], Any]) -> Any:
    """Re-render only when select(env) changes."""
    env = _current("use_env").rec.env
    value, set_value = use_state(lambda: select(env.get()))

    def sub() -> Callable[[], None]:
        set_value(select(env.get()))  # env may have changed between render and effect
        return env.subscribe(lambda: set_value(select(env.get())))

    use_effect(sub, [id(env)])
    return value


def use_window_dimensions():
    """`{"width", "height", "scale", "fontScale"}`, re-rendering on rotation / resize."""
    return _use_env(lambda e: {"width": e["window"]["width"], "height": e["window"]["height"],
                               "scale": e["scale"], "fontScale": e["font_scale"], "font_scale": e["font_scale"]})


def use_color_scheme() -> str:
    """"light" or "dark"."""
    return _use_env(lambda e: e["color_scheme"])


def use_breakpoint() -> str:
    """Active responsive breakpoint ("xs", "sm", "md", "lg", "xl", "xxl" by default, see `pyxpo.responsive`).
    Re-renders only when the window crosses a breakpoint."""
    from . import responsive
    return _use_env(lambda e: (responsive.breakpoint_for(e["window"]["width"] or 0), responsive.version()))[0]


def use_breakpoint_value(values: Any, default: Any = None) -> Any:
    """The value of a breakpoint map for the current window, mobile first:
    `use_breakpoint_value({"base": 1, "md": 2, "xl": 4})`. A plain value comes back as is."""
    from . import responsive
    return responsive.pick(values, use_breakpoint(), default)


def use_media_query(up: Optional[str] = None, down: Optional[str] = None, *, only: Optional[str] = None,
                    min_width: Optional[float] = None, max_width: Optional[float] = None,
                    orientation: Optional[str] = None) -> bool:
    """CSS-like media query against the window: `use_media_query("md")` is True from md up,
    `use_media_query(down="lg")` below lg, `use_media_query(only="md")`, `use_media_query(min_width=600)`,
    `use_media_query(orientation="landscape")`. Conditions combine with AND. Re-renders only when the result flips."""
    from . import responsive

    def test(e: Any) -> bool:
        w, h = e["window"]["width"] or 0, e["window"]["height"] or 0
        return responsive.query(responsive.breakpoint_for(w), w, h, up_=up, down_=down, only=only,
                                min_width=min_width, max_width=max_width, orientation=orientation)
    return _use_env(test)


SafeAreaInsetsContext = create_context(None)  # set by `pyxpo.safe_area.SafeAreaProvider`; None means "read the device"
SafeAreaFrameContext = create_context(None)


def use_safe_area_insets():
    """`{"top", "right", "bottom", "left"}` in dp."""
    override = use_context(SafeAreaInsetsContext)
    live = _use_env(lambda e: dict(e["insets"]))
    return live if override is None else override


def use_safe_area_frame():
    """`{"x", "y", "width", "height"}` of the safe-area root in dp."""
    override = use_context(SafeAreaFrameContext)
    live = _use_env(lambda e: {"x": 0, "y": 0, "width": e["window"]["width"], "height": e["window"]["height"]})
    return live if override is None else override


def _use_keyboard_state():
    return _use_env(lambda e: dict(e["keyboard"]))


useWindowDimensions = use_window_dimensions
useColorScheme = use_color_scheme
useSafeAreaInsets = use_safe_area_insets
useSafeAreaFrame = use_safe_area_frame
useBreakpoint = use_breakpoint
useBreakpointValue = use_breakpoint_value
useMediaQuery = use_media_query
