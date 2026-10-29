"""`Tabs` navigator: bottom tab bar over lazily mounted, kept-alive screens."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ...component import component
from ...components.pressable import Pressable
from ...components.text import Text
from ...components.view import View
from ...hooks import use_ref, use_safe_area_insets
from ..screen import Screen, route_element, route_options, use_navigator
from ..theme import useTheme
from .header import Header, TopInset
from .stack import FILL, HIDDEN


@component
def TabBar(items: Any = (), index: int = 0, on_select: Any = None, style: Any = None):
    """`items`: dicts `{key, label, icon (element or callable({color, size, focused})), badge}`."""
    c = useTheme()["colors"]
    inset = use_safe_area_insets()["bottom"]
    cells: List[Any] = []
    for i, it in enumerate(items):
        on = i == index
        col = it.get("activeTintColor", c["primary"]) if on else it.get("inactiveTintColor", "#8E8E93")
        icon = it.get("icon")
        icon = icon({"color": col, "size": 24, "focused": on}) if callable(icon) else icon
        badge = it.get("badge")
        pill = (View(Text(str(badge), style={"fontSize": 10, "color": "#FFFFFF"}),
                     style={"minWidth": 16, "height": 16, "borderRadius": 8, "alignItems": "center",
                            "justifyContent": "center", "paddingHorizontal": 3, "backgroundColor": c["notification"]})
                if badge not in (None, False) else None)
        label = Text(it["label"], style={"fontSize": 11, "marginTop": 3, "color": col})
        if icon is not None:  # pill rides the icon's top-right corner
            body = (View(icon, View(pill, style={"position": "absolute", "top": -4, "right": -10})
                         if pill is not None else None), label)
        elif pill is not None:  # no icon: pill sits beside the label
            body = (View(label, View(pill, style={"marginLeft": 4, "marginTop": 3}),
                         style={"flexDirection": "row", "alignItems": "center"}),)
        else:
            body = (label,)
        cells.append(Pressable(
            *body,
            on_press=(lambda i=i: on_select(i)), key=it["key"], accessibility_role="tab", accessibility_label=str(it["label"]),
            accessibility_state={"selected": on},
            style={"flex": 1, "alignItems": "center", "justifyContent": "center", "paddingVertical": 6}))
    return View(*cells, style=[{"flexDirection": "row", "height": 56 + inset, "paddingBottom": inset,
                                "backgroundColor": c["card"], "borderTopWidth": 1, "borderColor": c["border"]}, style])


@component
def Tabs(*children, screen_options: Any = None, initial_route_name: Optional[str] = None, tab_bar: Any = None):
    """`tab_bar(props)` replaces the bar (React Navigation's `tabBar`): props are `items`, `index`, `on_select`,
    `position` and `options` (the focused route's). Option `tabBarPosition` is "bottom" (default) or "left", the
    start side (it flips with the layout direction), for a rail or sidebar on a wide window."""
    rt, nav, node, declared = use_navigator("tabs", children, initial_route_name)
    bg = useTheme()["colors"]["background"]
    seen = use_ref(set())
    routes = node["routes"]
    cur = node["index"]
    seen.current.add(routes[cur]["key"])
    items, pages = [], []
    for i, r in enumerate(routes):
        o = route_options(rt, r, screen_options, declared)
        if o.get("href", True) is None:  # `href: null` hides the tab (expo-router)
            continue
        items.append({"key": r["key"], "label": o.get("tabBarLabel", o.get("title", r["name"])),
                      "icon": o.get("tabBarIcon"), "badge": o.get("tabBarBadge"),
                      "activeTintColor": o.get("tabBarActiveTintColor"), "inactiveTintColor": o.get("tabBarInactiveTintColor")})
        items[-1] = {k: v for k, v in items[-1].items() if v is not None}
        if r["key"] not in seen.current and o.get("lazy", True):
            continue
        show = o.get("headerShown", True)
        pages.append(View(Header(title=o.get("title", r["name"]), options=o) if show else None,
                          View(TopInset.Provider(route_element(nav, node, r), value=not show), style={"flex": 1}),
                          key=r["key"], style=[FILL, {"backgroundColor": bg}, None if i == cur else HIDDEN]))
    cur_item = next((n for n, it in enumerate(items) if it["key"] == routes[cur]["key"]), 0)
    cur_opts = route_options(rt, routes[cur], screen_options, declared)
    position = cur_opts.get("tabBarPosition", "bottom")
    if position not in ("bottom", "left"):
        raise ValueError("tabBarPosition must be 'bottom' or 'left', got %r" % (position,))
    keys = [it["key"] for it in items]

    def select(n: int) -> None:
        rt.store.set_index(node["key"], next(i for i, r in enumerate(routes) if r["key"] == keys[n]))

    if tab_bar is not None:
        bar = tab_bar({"items": items, "index": cur_item, "on_select": select, "position": position, "options": cur_opts})
    else:
        bar = TabBar(items=items, index=cur_item, style=cur_opts.get("tabBarStyle"), on_select=select)
    scenes = View(*pages, style={"flex": 1})
    if position == "left":
        return View(bar, scenes, style={"flex": 1, "flexDirection": "row"})
    return View(scenes, bar, style={"flex": 1})


Tabs.Screen = Screen
