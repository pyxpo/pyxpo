"""Rendering of route trees: layout/page hosts, the `Screen` declaration and helpers every navigator layout uses."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..component import Component, ErrorBoundary, component
from ..components.text import Text
from ..components.view import View
from ..hooks import create_context, use_context, use_effect
from .discovery import Navigator, Screen as RouteScreen, load_module, route_component
from .hooks import Navigation
from .runtime import NavigatorContext, RouteContext, Runtime, RuntimeContext
from .store import Node

# Drawer hands nested Stacks a callable(token, locked): a pushed Stack owns the left-edge swipe.
EdgeLock = create_context(None)


@component
def Screen(name: Optional[str] = None, options: Any = None, initial_params: Any = None, redirect: bool = False,
           listeners: Any = None):
    """`Stack.Screen`/`Tabs.Screen`/`Drawer.Screen`. In a layout it declares a screen (`name`, `options`); inside a page
    it sets that route's options and renders nothing."""
    rt = use_context(RuntimeContext)
    route = use_context(RouteContext)
    key = route["key"] if route else None
    opts = options(route) if callable(options) else options

    def apply() -> Any:
        if rt is None or key is None or name is not None or not opts:
            return None
        rt.set_options(key, opts)
        return lambda: rt.set_options(key, None)
    use_effect(apply, [key, opts])
    return None


def declared_screens(children: Sequence[Any]) -> Dict[str, Any]:
    return {c.props["name"]: c.props for c in children
            if getattr(c, "type", None) is Screen and c.props.get("name") is not None}


def route_options(rt: Runtime, route: Dict[str, Any], screen_options: Any, declared: Dict[str, Any]) -> Dict[str, Any]:
    """Layout `screenOptions` < `<X.Screen name=...>` options < options set from inside the page."""
    info = {"route": {"key": route["key"], "name": route["name"], "params": route["params"]}}
    out: Dict[str, Any] = {}
    for o in (screen_options, (declared.get(route["name"]) or {}).get("options"), rt.options.get(route["key"])):
        o = o(info) if callable(o) else o
        if o:
            out.update(o)
    return out


def use_navigator(type: str, children: Sequence[Any], initial: Optional[str]) -> Tuple[Runtime, Navigator, Node, Dict[str, Any]]:
    """Register this layout's navigator type with the store and return (runtime, navigator, node, declared screens)."""
    rt = use_context(RuntimeContext)
    ctx = use_context(NavigatorContext)
    nav: Navigator = ctx["nav"]
    declared = declared_screens(children)
    rt.store.register_navigator(nav.path, type, {"initialRouteName": initial, "order": list(declared)})
    node = rt.node(ctx["key"])
    if node is None:  # state changed under us (hot reload removed the navigator): show the focused state
        node = rt.store.state
    return rt, nav, node, declared


def route_element(nav: Navigator, node: Node, route: Dict[str, Any]) -> Any:
    """Element for one route of `node`: a page, a nested navigator, or the not-found fallback."""
    scr = nav.screen(route["name"])
    if scr is None:
        inner: Any = NotFound()
    elif scr.navigator is not None:
        st = route.get("state")
        inner = NavigatorHost(nav=scr.navigator, node_key=st["key"]) if st else None
    else:
        inner = PageHost(screen=scr)
    ctx = {"key": route["key"], "name": route["name"], "node_key": node["key"], "nav": nav}
    return RouteContext.Provider(inner, value=ctx, key=route["key"])


def _boundary_fallback(mod: Any):
    eb = getattr(mod, "ErrorBoundary", None)
    return (lambda error, reset: eb(error=error, retry=reset)) if eb is not None else None


@component
def PageHost(screen: Optional[RouteScreen] = None):
    rt = use_context(RuntimeContext)
    mod = load_module(screen.module_name, screen.file, rt.root_dir)
    page = route_component(mod)  # resolved every render: hot reload swaps the module's component
    fb = _boundary_fallback(mod)
    return ErrorBoundary(page(), fallback=fb) if fb is not None else page()


@component
def NavigatorHost(nav: Optional[Navigator] = None, node_key: str = ""):
    rt = use_context(RuntimeContext)
    if nav.layout_module is None:
        from .layouts.slot import Slot
        layout: Any = Slot
        fb = None
    else:
        mod = load_module(nav.layout_module, nav.layout_file, rt.root_dir)
        layout, fb = route_component(mod), _boundary_fallback(mod)
    el = NavigatorContext.Provider(layout(), value={"nav": nav, "key": node_key})
    return ErrorBoundary(el, fallback=fb) if fb is not None else el


@component
def NotFound():
    rt = use_context(RuntimeContext)
    return View(Text("Unmatched Route", style={"fontSize": 20, "fontWeight": "600", "textAlign": "center"}),
                Text(rt.store.pathname, style={"marginTop": 8, "textAlign": "center", "color": "#8E8E93"}),
                style={"flex": 1, "alignItems": "center", "justifyContent": "center", "padding": 24})
