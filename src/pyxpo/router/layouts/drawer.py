"""`Drawer` navigator: side drawer with edge-swipe, scrim and a default item list."""
from __future__ import annotations

from typing import Any, Optional

from ...animated import Animated, Easing, use_animated_value
from ...apis.pan_responder import PanResponder
from ...component import component
from ...components.pressable import Pressable
from ...components.text import Text
from ...components.view import View
from ...hooks import use_effect, use_memo, use_ref, use_safe_area_insets, use_state, use_window_dimensions
from ...vector_icons import Feather
from ..screen import EdgeLock, Screen, route_element, route_options, use_navigator
from ..theme import useTheme
from .header import Header, TopInset
from .stack import FILL, HIDDEN


@component
def DrawerItems(items: Any = (), index: int = 0, on_select: Any = None, title: str = ""):
    c = useTheme()["colors"]
    inset = use_safe_area_insets()
    rows = []
    for i, it in enumerate(items):
        on = i == index
        col = c["primary"] if on else c["text"]
        rows.append(Pressable(Text(it["label"], style={"fontSize": 15, "fontWeight": "500", "color": col}),
                              on_press=lambda i=i: on_select(i), key=it["key"], accessibility_role="menuitem", accessibility_label=str(it["label"]),
                              accessibility_state={"selected": on},
                              style={"paddingVertical": 12, "paddingHorizontal": 16, "marginHorizontal": 8,
                                     "borderRadius": 8, "backgroundColor": c["border"] if on else None}))
    return View(Text(title, style={"fontSize": 20, "fontWeight": "700", "padding": 16,
                                   "paddingTop": 16 + inset["top"], "color": c["text"]})
                if title else View(style={"height": 16 + inset["top"]}), *rows,
                style={"flex": 1, "paddingBottom": inset["bottom"]})


@component
def Drawer(*children, screen_options: Any = None, initial_route_name: Optional[str] = None,
           drawer_content: Any = None, drawer_title: str = "", drawer_width: float = 300):
    rt, nav, node, declared = use_navigator("drawer", children, initial_route_name)
    c = useTheme()["colors"]
    win = use_window_dimensions()
    routes, cur, is_open = node["routes"], node["index"], bool(node.get("drawer_open"))
    shown, set_shown = use_state(False)  # panel + scrim stay mounted while the close animation runs
    seen = use_ref(set())
    locks = use_ref(set())
    _, bump = use_state(0)
    live = use_ref(False)
    live.current = is_open
    p = use_animated_value(0.0)
    width = min(float(drawer_width), win["width"] * 0.82)
    tx, scrim_op = use_memo(lambda: (p.interpolate([0, 1], [-width, 0]), p.interpolate([0, 1], [0, 0.5])), [width])
    set_open = lambda v: rt.store.set_drawer_open(node["key"], v)  # noqa: E731
    if is_open and not shown:
        set_shown(True)

    def animate() -> None:
        if is_open:
            Animated.timing(p, 1, 260, Easing.out(Easing.cubic)).start()
        elif shown:
            Animated.timing(p, 0, 200, Easing.in_(Easing.cubic)).start(
                lambda r: None if live.current else set_shown(False))
    use_effect(animate, [is_open, shown])

    def lock_edge(token: Any, on: bool) -> None:
        if (token in locks.current) != on:
            (locks.current.add if on else locks.current.discard)(token)
            bump(lambda v: v + 1)
    lock_ref = use_ref(lock_edge)
    edge = use_ref(PanResponder.create({"onPanResponderEnd": lambda e, g: set_open(True) if g.dx > 50 or g.vx > 500 else None}))
    scrim_pan = use_ref(PanResponder.create({"onPanResponderEnd": lambda e, g: set_open(False)
                                             if abs(g.dx) < 8 or g.dx < -50 or g.vx < -500 else None}))
    seen.current.add(routes[cur]["key"])
    items = [{"key": r["key"], "label": route_options(rt, r, screen_options, declared).get(
        "drawerLabel", route_options(rt, r, screen_options, declared).get("title", r["name"]))} for r in routes]
    pages = []
    for i, r in enumerate(routes):
        if r["key"] not in seen.current:
            continue
        o = route_options(rt, r, screen_options, declared)
        show = o.get("headerShown", True)
        menu = Pressable(Feather(name="menu", size=22, color=o.get("headerTintColor") or c["text"]),
                         on_press=lambda: set_open(True), accessibility_label="Menu",
                         style={"width": 40, "height": 40, "alignItems": "center", "justifyContent": "center"})
        pages.append(View(Header(title=o.get("title", r["name"]), options=dict({"headerLeft": menu}, **o)) if show else None,
                          View(TopInset.Provider(route_element(nav, node, r), value=not show), style={"flex": 1}),
                          key=r["key"], style=[FILL, {"backgroundColor": c["background"]}, None if i == cur else HIDDEN]))
    layers = [View(*pages, style={"flex": 1})]
    if shown:
        select = lambda i: rt.store.set_index(node["key"], i)  # noqa: E731
        content = (drawer_content(items=items, index=cur, on_select=select) if drawer_content is not None
                   else DrawerItems(items=items, index=cur, on_select=select, title=drawer_title))
        layers.append(View(View(style={"flex": 1, "backgroundColor": "#000000", "opacity": scrim_op}), key="scrim",
                           style=FILL, **scrim_pan.current.panHandlers))
        layers.append(View(content, key="panel",
                           style={"position": "absolute", "left": 0, "top": 0, "bottom": 0, "width": width,
                                  "backgroundColor": c["card"], "translateX": tx, "shadowColor": "#000000",
                                  "shadowOpacity": 0.3, "shadowRadius": 12, "elevation": 16}))
    elif not locks.current:
        layers.append(View(key="edge", style={"position": "absolute", "left": 0, "top": 0, "bottom": 0, "width": 16},
                           **edge.current.panHandlers))
    return EdgeLock.Provider(View(*layers, style={"flex": 1, "overflow": "hidden"}), value=lock_ref.current)


Drawer.Screen = Screen
