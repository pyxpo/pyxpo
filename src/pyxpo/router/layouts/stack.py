"""`Stack` navigator: native NavStack (slide push/pop, edge-swipe back) with a react-navigation style header.

On web the stack acts like page navigation: the new route replaces the old one at once (no slide, no edge swipe) and
the browser's back button goes back. Routes below the top stay mounted but hidden, so their scroll position and state
come back on Back, as in an SPA."""
from __future__ import annotations

from typing import Any, Dict, Optional

from ...component import component
from ...components.view import View
from ...element import _host
from ...hooks import use_context, use_effect, use_ref
from ..runtime import on_web
from ..screen import EdgeLock, Screen, route_element, route_options, use_navigator
from ..theme import useTheme
from .header import Header, TopInset

_NavStack = _host("NavStack")
FILL = {"position": "absolute", "left": 0, "top": 0, "right": 0, "bottom": 0}
HIDDEN = {"display": "none"}


@component
def Stack(*children, screen_options: Any = None, initial_route_name: Optional[str] = None):
    rt, nav, node, declared = use_navigator("stack", children, initial_route_name)
    bg = useTheme()["colors"]["background"]
    routes = node["routes"]
    top = routes[-1]
    below = routes[-2] if len(routes) > 1 else None  # stays laid out: native slides/drags over it
    lock = use_context(EdgeLock)
    tok = use_ref(object())
    deep = len(routes) > 1
    web = on_web()

    def sync_lock() -> Any:
        if lock is None:
            return None
        lock(tok.current, deep)
        return lambda: lock(tok.current, False)
    use_effect(sync_lock, [deep, lock])

    def view(r: Dict[str, Any], idx: int):
        o = route_options(rt, r, screen_options, declared)
        show = o.get("headerShown", True)
        title = o.get("title", r["name"])
        # Web: the page hides the routes below the top itself (`visibility`), which keeps their scroll offsets.
        shown = web or r is top or r is below
        header = Header(title=title, can_back=idx > 0, on_back=lambda k=r["key"]: rt.store.pop(k),
                        options=o) if show else None
        body = View(TopInset.Provider(route_element(nav, node, r), value=not show), style={"flex": 1})
        return View(header, body, key=r["key"],
                    style=[FILL, {"background_color": bg}, o.get("contentStyle"), None if shown else HIDDEN])

    pages = [view(r, i) for i, r in enumerate(routes)]
    animated = bool(routes) and not web and rt_animation(rt, top, screen_options, declared)
    gesture = deep and not web and _gesture(rt, top, screen_options, declared)
    return _NavStack(*pages, animated=animated, gesture=gesture,
                     on_pop_gesture=lambda *_: rt.store.pop(top["key"]), style={"flex": 1, "overflow": "hidden"})


def rt_animation(rt, top, screen_options, declared) -> bool:
    return route_options(rt, top, screen_options, declared).get("animation", "default") != "none"


def _gesture(rt, top, screen_options, declared) -> bool:
    return bool(route_options(rt, top, screen_options, declared).get("gestureEnabled", True))


Stack.Screen = Screen
