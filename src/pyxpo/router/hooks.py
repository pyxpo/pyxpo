"""expo-router hooks."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from ..hooks import use_context, use_effect, use_memo
from .router import Router, router
from .runtime import RouteContext, RuntimeContext


def _rt() -> Any:
    rt = use_context(RuntimeContext)
    if rt is None:
        raise RuntimeError("router hooks must be used inside the app rendered by pyxpo.router")
    return rt


def _route() -> Dict[str, Any]:
    ctx = use_context(RouteContext)
    if ctx is None:
        raise RuntimeError("this hook must be used inside a route")
    return ctx


def useRouter() -> Router:
    _rt()
    return router


def useLocalSearchParams() -> Dict[str, Any]:
    """Params of the route this component belongs to (path params + query; values are str or list of str)."""
    return _rt().store.route_params(_route()["key"])


def useGlobalSearchParams() -> Dict[str, Any]:
    """Params of the focused route, wherever this component is."""
    return _rt().store.params


def usePathname() -> str:
    return _rt().store.pathname


def useSegments() -> List[str]:
    return _rt().store.segments


class Navigation:
    """react-navigation style handle of one route (`useNavigation()`)."""

    def __init__(self, rt: Any, ctx: Dict[str, Any]) -> None:
        self._rt, self._ctx = rt, ctx
        self.navigate, self.push, self.replace = router.navigate, router.push, router.replace

    def setOptions(self, options: Dict[str, Any]) -> None:
        merged = dict(self._rt.options.get(self._ctx["key"], {}))
        merged.update(options)
        self._rt.set_options(self._ctx["key"], merged)

    def goBack(self) -> None:
        self._rt.store.pop(self._ctx["key"])

    def canGoBack(self) -> bool:
        return router.canGoBack()

    def setParams(self, params: Dict[str, Any]) -> None:
        self._rt.store.set_params(params, self._ctx["key"])

    def isFocused(self) -> bool:
        return self._rt.store.is_focused(self._ctx["key"])

    def addListener(self, event: str, fn: Callable[[], Any]) -> Callable[[], None]:
        if event not in ("focus", "blur"):
            raise ValueError("addListener: 'focus' or 'blur', got %r" % (event,))
        return self._rt.store.add_listener(self._ctx["key"], event, fn)

    def getParent(self) -> Optional["Navigation"]:
        node = self._rt.node(self._ctx["node_key"])
        owner = node and self._parent_route(node["key"])
        return Navigation(self._rt, owner) if owner else None

    def _parent_route(self, node_key: str) -> Optional[Dict[str, Any]]:
        def walk(node: Dict[str, Any], parent: Optional[Dict[str, Any]]) -> Any:
            if node["key"] == node_key:
                return parent
            for r in node["routes"]:
                st = r.get("state")
                if st is not None:
                    hit = walk(st, {"key": r["key"], "name": r["name"], "node_key": node["key"]})
                    if hit is not None:
                        return hit
            return None
        return walk(self._rt.store.state, None)

    def _drawer(self) -> Optional[Dict[str, Any]]:
        def walk(node: Dict[str, Any], path: List[Dict[str, Any]]) -> Any:
            if node["key"] == self._ctx["node_key"]:
                return path + [node]
            for r in node["routes"]:
                st = r.get("state")
                hit = st is not None and walk(st, path + [node])
                if hit:
                    return hit
            return None
        chain = walk(self._rt.store.state, []) or []
        return next((n for n in reversed(chain) if n["type"] == "drawer"), None)

    def openDrawer(self) -> None:
        d = self._drawer()
        d and self._rt.store.set_drawer_open(d["key"], True)

    def closeDrawer(self) -> None:
        d = self._drawer()
        d and self._rt.store.set_drawer_open(d["key"], False)

    def toggleDrawer(self) -> None:
        d = self._drawer()
        d and self._rt.store.set_drawer_open(d["key"], not d.get("drawer_open"))

    set_options, open_drawer, close_drawer, toggle_drawer = setOptions, openDrawer, closeDrawer, toggleDrawer
    go_back, can_go_back, set_params = goBack, canGoBack, setParams
    is_focused, add_listener, get_parent = isFocused, addListener, getParent


def useNavigation(parent: Optional[str] = None) -> Navigation:
    rt, ctx = _rt(), _route()
    nav = use_memo(lambda: Navigation(rt, ctx), [rt, ctx["key"], ctx["node_key"]])
    return nav.getParent() or nav if parent == "/" else nav


def useIsFocused() -> bool:
    return _rt().store.is_focused(_route()["key"])


def useFocusEffect(effect: Callable[[], Any]) -> None:
    """Run `effect` while the route is focused; its returned cleanup runs on blur. Wrap it in useCallback."""
    focused = useIsFocused()
    use_effect(lambda: effect() if focused else None, [focused, effect])


use_router, use_local_search_params, use_global_search_params = useRouter, useLocalSearchParams, useGlobalSearchParams
use_pathname, use_segments, use_navigation = usePathname, useSegments, useNavigation
use_is_focused, use_focus_effect = useIsFocused, useFocusEffect
