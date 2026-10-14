"""Navigation: a screen stack (`Stack`) and bottom tabs (`Tabs`), written in Python on top of View.

    Stack({"Home": Home, "Detail": Detail}, initial="Home")

Each screen is a function `screen(navigation, params)` (or a component taking those props). Screens
below the top stay mounted (their state survives) and are hidden with `display: none`.
`use_navigation()` returns the nearest navigator's `Navigation` from any descendant.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .component import component
from .element import Text, View
from .hooks import create_context, use_context, use_ref, use_state
from .style import flatten
from .theme import use_theme

_FILL = {"position": "absolute", "left": 0, "top": 0, "right": 0, "bottom": 0}


class Route:
    __slots__ = ("key", "name", "params")

    def __init__(self, key: int, name: str, params: Dict[str, Any]) -> None:
        self.key, self.name, self.params = key, name, params


class Navigation:
    """Handle passed to screens. All methods are safe to call from event handlers."""

    def __init__(self, nav: "_Nav", route: Optional[Route]) -> None:
        self._nav = nav
        self.route = route
        self.params: Dict[str, Any] = route.params if route is not None else {}
        self.name = route.name if route is not None else ""

    def navigate(self, name: str, **params: Any) -> None:
        self._nav.navigate(name, params)

    push = navigate

    def go_back(self) -> None:
        self._nav.go_back()

    pop = go_back

    def pop_to_top(self) -> None:
        self._nav.pop_to_top()

    def replace(self, name: str, **params: Any) -> None:
        self._nav.replace(name, params)

    def reset(self, name: str, **params: Any) -> None:
        self._nav.reset(name, params)

    def set_params(self, **params: Any) -> None:
        if self.route is not None:
            self._nav.set_params(self.route.key, params)

    def can_go_back(self) -> bool:
        return self._nav.can_go_back()


class _Nav:
    """Mutable stack state shared by the navigator component and its Navigation handles."""

    def __init__(self, names: List[str], initial: str, set_tick: Callable[[Any], None]) -> None:
        self.names = names
        self._tick = set_tick
        self._n = 0
        self.stack: List[Route] = []
        self.stack.append(self._route(initial, {}))

    def _route(self, name: str, params: Dict[str, Any]) -> Route:
        if name not in self.names:
            raise KeyError("no screen named %r (known: %s)" % (name, ", ".join(self.names)))
        self._n += 1
        return Route(self._n, name, dict(params))

    def _changed(self) -> None:
        self._tick(lambda v: v + 1)

    def navigate(self, name: str, params: Dict[str, Any]) -> None:
        self.stack.append(self._route(name, params))
        self._changed()

    def go_back(self) -> None:
        if len(self.stack) > 1:
            self.stack.pop()
            self._changed()

    def pop_to_top(self) -> None:
        if len(self.stack) > 1:
            del self.stack[1:]
            self._changed()

    def replace(self, name: str, params: Dict[str, Any]) -> None:
        self.stack[-1] = self._route(name, params)
        self._changed()

    def reset(self, name: str, params: Dict[str, Any]) -> None:
        self.stack[:] = [self._route(name, params)]
        self._changed()

    def set_params(self, key: int, params: Dict[str, Any]) -> None:
        for r in self.stack:
            if r.key == key:
                r.params.update(params)
        self._changed()

    def can_go_back(self) -> bool:
        return len(self.stack) > 1


class _TabNav(_Nav):
    """Tabs: navigate/replace/reset switch the selected tab (name is validated)."""

    select: Callable[[str], None] = staticmethod(lambda name: None)  # type: ignore[assignment]

    def navigate(self, name: str, params: Dict[str, Any]) -> None:
        self._route(name, params)  # raises KeyError for an unknown tab
        self.select(name)

    replace = navigate
    reset = navigate


_NavContext = create_context(None)


def use_navigation() -> Navigation:
    nav = use_context(_NavContext)
    if nav is None:
        raise RuntimeError("use_navigation() must be called inside a Stack or Tabs screen")
    return nav


def _call(screen: Any, nav: Navigation, params: Dict[str, Any]) -> Any:
    return screen(navigation=nav, params=params)


@component
def _Screen(screen: Any = None, navigation: Any = None, params: Any = None):
    return _call(screen, navigation, params)


def _title(name: str, options: Dict[str, Any]) -> str:
    return str(options.get("title", name))


@component
def _Header(title: str = "", can_back: bool = False, on_back: Any = None, header_style: Any = None,
            title_style: Any = None, back_label: str = "‹", right: Any = None):
    from .ui import Pressable
    c = use_theme()["colors"]
    bar = {"height": 48, "flex_direction": "row", "align_items": "center", "padding_horizontal": 4,
           "background_color": c["surface"], "border_bottom_width": 1, "border_color": c["border"]}
    return View(
        Pressable(Text(back_label, style={"font_size": 30, "color": c["primary"], "margin_top": -4}),
                  on_press=on_back, accessibility_label="Back",
                  style={"width": 40, "height": 40, "align_items": "center", "justify_content": "center"})
        if can_back else View(style={"width": 8}),
        Text(title, style=[{"flex": 1, "font_size": 17, "font_weight": "600", "color": c["text"]}, title_style]),
        right if right is not None else None,
        style=[bar, header_style])


@component
def Stack(screens: Optional[Dict[str, Any]] = None, initial: Optional[str] = None,
          screen_options: Optional[Dict[str, Dict[str, Any]]] = None, header: bool = True,
          header_style: Any = None, title_style: Any = None, style: Any = None):
    """Stack navigator. `screens` maps names to screen functions; `initial` defaults to the first one.
    `screen_options[name]` accepts `title`, `header` (bool) and `header_right` (element)."""
    screens = screens or {}
    opts = screen_options or {}
    names = list(screens)
    bg = use_theme()["colors"]["background"]
    _, tick = use_state(0)  # hooks before any early return: `screens` may toggle between empty and not
    holder = use_ref(None)
    if not names:
        return View(style=style)
    if holder.current is None:
        holder.current = _Nav(names, initial if initial in screens else names[0], tick)
    nav: _Nav = holder.current
    nav.names = names
    # Drop routes whose screen was removed from `screens` (avoids KeyError on render).
    live = [r for r in nav.stack if r.name in screens]
    if not live:
        live = [nav._route(initial if initial in screens else names[0], {})]
    if len(live) != len(nav.stack):
        nav.stack[:] = live
    top = nav.stack[-1]
    kids = []
    for r in nav.stack:
        o = opts.get(r.name, {})
        handle = Navigation(nav, r)
        on_top = r is top
        show_header = header and o.get("header", True)
        # Each screen gets its own context value so use_navigation() sees its own route and params.
        kids.append(_NavContext.Provider(View(
            _Header(title=_title(r.name, o), can_back=nav.can_go_back() and r is not nav.stack[0],
                    on_back=nav.go_back, header_style=header_style, title_style=title_style,
                    right=o.get("header_right")) if show_header else None,
            View(_Screen(screen=screens[r.name], navigation=handle, params=r.params), style={"flex": 1}),
            style=[_FILL, {"background_color": bg}, None if on_top else {"display": "none"}]),
            value=handle, key="r%d" % r.key))
    return _NavContext.Provider(View(*kids, style=[{"flex": 1}, style]), value=Navigation(nav, top))


@component
def Tabs(screens: Optional[Dict[str, Any]] = None, initial: Optional[str] = None,
         screen_options: Optional[Dict[str, Dict[str, Any]]] = None, tab_bar_style: Any = None,
         active_color: Optional[str] = None, inactive_color: Optional[str] = None, style: Any = None):
    """Bottom tab navigator. Tabs mount lazily on first visit and then stay mounted.
    `screen_options[name]` accepts `title` and `icon` (a string/glyph or element shown above the label)."""
    from .ui import Pressable
    c = use_theme()["colors"]
    active_color = active_color or c["primary"]
    inactive_color = inactive_color or c["text_muted"]
    screens = screens or {}
    opts = screen_options or {}
    names = list(screens)
    # Hooks before any early return: `screens` may toggle between empty and not.
    cur, set_cur = use_state(initial)
    seen = use_ref(set())
    holder = use_ref(None)
    _, tick = use_state(0)
    if not names:
        return View(style=style)
    if cur not in screens:  # first render, or the current tab was removed
        cur = initial if initial in screens else names[0]
    seen.current.add(cur)
    if holder.current is None:
        holder.current = _TabNav(names, cur, tick)
    nav: _TabNav = holder.current
    nav.names = names
    nav.select = set_cur
    pages = []
    for name in names:
        if name not in seen.current:
            continue
        handle = Navigation(nav, Route(0, name, {}))
        pages.append(_NavContext.Provider(
            View(_Screen(screen=screens[name], navigation=handle, params={}),
                 style=[_FILL, {"background_color": c["background"]}, None if name == cur else {"display": "none"}]),
            value=handle, key=name))
    items = []
    for name in names:
        o = opts.get(name, {})
        on = name == cur
        color = active_color if on else inactive_color
        icon = o.get("icon")
        items.append(Pressable(
            Text(icon, style={"font_size": 20, "color": color}) if isinstance(icon, str) else icon,
            Text(_title(name, o), style={"font_size": 11, "color": color, "margin_top": 2}),
            on_press=(lambda n=name: set_cur(n)), accessibility_role="tab",
            accessibility_state={"selected": on}, key=name,
            style={"flex": 1, "align_items": "center", "justify_content": "center", "padding_vertical": 6}))
    bar = {"flex_direction": "row", "height": 56, "background_color": c["surface"], "border_top_width": 1,
           "border_color": c["border"]}
    return _NavContext.Provider(
        View(View(*pages, style={"flex": 1}), View(*items, style=[bar, tab_bar_style]),
             style=[{"flex": 1}, style]),
        value=Navigation(nav, Route(0, cur, {})))
