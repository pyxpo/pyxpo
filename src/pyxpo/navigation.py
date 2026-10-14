"""Navigation, written in Python on top of View: `Stack`, `Tabs` (bottom), `TopTabs` and `Drawer`.

    Stack({"Home": Home, "Detail": Detail}, initial="Home")
    Drawer({"Inbox": Inbox, "Sent": Sent})
    TopTabs({"Feed": Feed, "Popular": Popular})

Each screen is a function `screen(navigation, params)` (or a component taking those props). Navigators nest:
a screen of a Drawer can be a Tabs whose tabs are Stacks. `navigation.navigate(name)` goes to the nearest
navigator that knows `name`; `navigation.parent` is the enclosing navigator and `open_drawer()` finds the
nearest Drawer. Hidden screens stay mounted (their state survives) with `display: none`. Android hardware
back pops the innermost Stack or closes an open Drawer.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .animated import Animated, Easing, use_animated_value
from .component import component
from .element import NavStack, ScrollView, Text, View
from .env import use_window_dimensions
from .hooks import create_context, use_context, use_effect, use_memo, use_ref, use_state
from .theme import use_theme
from .ui import use_pan_responder

_FILL = {"position": "absolute", "left": 0, "top": 0, "right": 0, "bottom": 0}
_HIDDEN = {"display": "none"}


class Route:
    __slots__ = ("key", "name", "params", "anim")

    def __init__(self, key: int, name: str, params: Dict[str, Any], anim: bool = False) -> None:
        self.key, self.name, self.params, self.anim = key, name, params, anim


class Navigation:
    """Handle passed to screens. All methods are safe to call from event handlers."""

    def __init__(self, nav: "_Nav", route: Optional[Route]) -> None:
        self._nav = nav
        self.route = route
        self.params: Dict[str, Any] = route.params if route is not None else {}
        self.name = route.name if route is not None else ""

    @property
    def parent(self) -> Optional["Navigation"]:
        """Handle of the enclosing navigator (None at the top level)."""
        return self._nav.parent

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

    def open_drawer(self) -> None:
        self._nav.open_drawer()

    def close_drawer(self) -> None:
        self._nav.close_drawer()

    def toggle_drawer(self) -> None:
        self._nav.toggle_drawer()


class _Nav:
    """Mutable stack state shared by the navigator component and its Navigation handles."""

    def __init__(self, names: List[str], initial: str, set_tick: Callable[[Any], None]) -> None:
        self.names = names
        self._tick = set_tick
        self._n = 0
        self.parent: Optional[Navigation] = None
        self.animate = False
        self.transitioning = False
        self.leaving: List[Route] = []
        self.stack: List[Route] = []
        self.stack.append(self._route(initial, {}))

    def _route(self, name: str, params: Dict[str, Any], anim: bool = False) -> Route:
        if name not in self.names:
            raise KeyError("no screen named %r (known: %s)" % (name, ", ".join(self.names)))
        self._n += 1
        return Route(self._n, name, dict(params), anim)

    def _changed(self) -> None:
        self._tick(lambda v: v + 1)

    def _bubble(self, name: str, params: Dict[str, Any]) -> bool:
        """Unknown screen: hand it to the parent navigator, if any."""
        if name not in self.names and self.parent is not None:
            self.parent.navigate(name, **params)
            return True
        return False

    def navigate(self, name: str, params: Dict[str, Any]) -> None:
        if self._bubble(name, params):
            return
        self.stack.append(self._route(name, params, self.animate))
        self.transitioning = self.animate
        self._changed()

    def _leave(self, routes: List[Route]) -> None:
        self.transitioning = False
        if self.animate and routes:
            self.leaving.append(routes[-1])

    def go_back(self) -> None:
        if len(self.stack) > 1:
            self._leave([self.stack.pop()])
            self._changed()

    def pop_to_top(self) -> None:
        if len(self.stack) > 1:
            gone = self.stack[1:]
            del self.stack[1:]
            self._leave(gone)
            self._changed()

    def replace(self, name: str, params: Dict[str, Any]) -> None:
        self.stack[-1] = self._route(name, params)
        self._changed()

    def reset(self, name: str, params: Dict[str, Any]) -> None:
        self.stack[:] = [self._route(name, params)]
        self.leaving.clear()
        self.transitioning = False
        self._changed()

    def set_params(self, key: int, params: Dict[str, Any]) -> None:
        for r in self.stack:
            if r.key == key:
                r.params.update(params)
        self._changed()

    def can_go_back(self) -> bool:
        return len(self.stack) > 1

    def enter_done(self, key: int) -> None:
        if self.transitioning and self.stack[-1].key == key:
            self.transitioning = False
            self._changed()

    def exit_done(self, key: int) -> None:
        n = len(self.leaving)
        self.leaving[:] = [r for r in self.leaving if r.key != key]
        if len(self.leaving) != n:
            self._changed()

    def open_drawer(self) -> None:
        if self.parent is not None:
            self.parent.open_drawer()

    def close_drawer(self) -> None:
        if self.parent is not None:
            self.parent.close_drawer()

    def toggle_drawer(self) -> None:
        if self.parent is not None:
            self.parent.toggle_drawer()


class _TabNav(_Nav):
    """Tabs/TopTabs/Drawer: navigate/replace/reset switch the selected screen (name is validated)."""

    select: Callable[[str], None] = staticmethod(lambda name: None)  # type: ignore[assignment]

    def navigate(self, name: str, params: Dict[str, Any]) -> None:
        if self._bubble(name, params):
            return
        self._route(name, params)  # raises KeyError for an unknown screen
        self.select(name)

    replace = navigate
    reset = navigate


class _DrawerNav(_TabNav):
    is_open = False
    set_open: Callable[[bool], None] = staticmethod(lambda v: None)  # type: ignore[assignment]

    def navigate(self, name: str, params: Dict[str, Any]) -> None:
        super().navigate(name, params)
        if name in self.names:
            self.set_open(False)

    replace = reset = navigate

    def open_drawer(self) -> None:
        self.set_open(True)

    def close_drawer(self) -> None:
        self.set_open(False)

    def toggle_drawer(self) -> None:
        self.set_open(not self.is_open)


_NavContext = create_context(None)
_EdgeLock = create_context(None)  # Drawer hands nested Stacks a callable(token, locked): a pushed Stack owns the left-edge swipe
_TopInset = create_context(True)  # False once an ancestor header already paints under the status bar


def use_navigation() -> Navigation:
    nav = use_context(_NavContext)
    if nav is None:
        raise RuntimeError("use_navigation() must be called inside a navigator screen")
    return nav


def _call(screen: Any, nav: Navigation, params: Dict[str, Any]) -> Any:
    return screen(navigation=nav, params=params)


@component
def _Screen(screen: Any = None, navigation: Any = None, params: Any = None):
    return _call(screen, navigation, params)


def _title(name: str, options: Dict[str, Any]) -> str:
    return str(options.get("title", name))


def _use_back(handler: Callable[[], bool]) -> None:
    """Register `handler` for Android hardware back while this navigator is mounted (innermost first)."""
    ref = use_ref(None)
    ref.current = handler

    def register() -> Any:
        from .modules import Back
        return Back.add(lambda: bool(ref.current()))
    use_effect(register, [])


@component
def _Header(title: str = "", can_back: bool = False, on_back: Any = None, header_style: Any = None,
            title_style: Any = None, back_label: str = "", right: Any = None, left: Any = None):
    from .ui import Pressable
    from .widgets import Icon
    from .env import use_safe_area_insets
    c = use_theme()["colors"]
    top = use_safe_area_insets()["top"] if use_context(_TopInset) else 0
    bar = {"height": 48 + top, "padding_top": top, "flex_direction": "row", "align_items": "center",
           "padding_horizontal": 4, "background_color": c["surface"], "border_bottom_width": 1, "border_color": c["border"]}
    if left is None:
        left = (Pressable(back_label and Text(back_label, style={"font_size": 30, "color": c["primary"]})
                          or Icon("chevron-left", size=26, color=c["primary"]),
                          on_press=on_back, accessibility_label="Back",
                          style={"width": 40, "height": 40, "align_items": "center", "justify_content": "center"})
                if can_back else View(style={"width": 8}))
    return View(
        left,
        Text(title, number_of_lines=1,
             style=[{"flex": 1, "font_size": 17, "font_weight": "600", "color": c["text"]}, title_style]),
        right if right is not None else None,
        style=[bar, header_style])


@component
def Stack(screens: Optional[Dict[str, Any]] = None, initial: Optional[str] = None,
          screen_options: Optional[Dict[str, Dict[str, Any]]] = None, header: bool = True,
          header_style: Any = None, title_style: Any = None, animate: bool = True, style: Any = None):
    """Stack navigator. `screens` maps names to screen functions; `initial` defaults to the first one.
    `screen_options[name]` accepts `title`, `header` (bool), `header_left` and `header_right` (elements).
    Pushes slide in from the right and pops slide out (`animate=False` turns that off)."""
    screens = screens or {}
    opts = screen_options or {}
    names = list(screens)
    bg = use_theme()["colors"]["background"]
    parent = use_context(_NavContext)
    _, tick = use_state(0)  # hooks before any early return: `screens` may toggle between empty and not
    holder = use_ref(None)
    _use_back(lambda: holder.current is not None and holder.current.can_go_back() and (holder.current.go_back() or True))
    lock = use_context(_EdgeLock)
    deep = holder.current is not None and len(holder.current.stack) > 1
    tok = use_ref(object())

    def sync_lock() -> Any:
        if lock is None:
            return None
        lock(tok.current, deep)
        return lambda: lock(tok.current, False)
    use_effect(sync_lock, [deep, lock])
    if not names:
        return View(style=style)
    if holder.current is None:
        holder.current = _Nav(names, initial if initial in screens else names[0], tick)
    nav: _Nav = holder.current
    nav.names, nav.parent, nav.animate = names, parent, animate
    # Drop routes whose screen was removed from `screens` (avoids KeyError on render).
    live = [r for r in nav.stack if r.name in screens]
    if not live:
        live = [nav._route(initial if initial in screens else names[0], {})]
    if len(live) != len(nav.stack):
        nav.stack[:] = live
    nav.leaving[:] = [r for r in nav.leaving if r.name in screens]
    top = nav.stack[-1]
    below = nav.stack[-2] if len(nav.stack) > 1 else None  # stays laid out: native slides/drags over it

    def route_view(r: Route):
        o = opts.get(r.name, {})
        handle = Navigation(nav, r)
        show_header = header and o.get("header", True)
        # Each screen gets its own context value so use_navigation() sees its own route and params.
        return _NavContext.Provider(
            View(
                _Header(title=_title(r.name, o), can_back=r is not nav.stack[0], on_back=nav.go_back,
                        header_style=header_style, title_style=title_style, left=o.get("header_left"),
                        right=o.get("header_right")) if show_header else None,
                View(_TopInset.Provider(_Screen(screen=screens[r.name], navigation=handle, params=r.params),
                                        value=not show_header), style={"flex": 1}),
                style=[_FILL, {"background_color": bg}, _HIDDEN if r is not top and r is not below else None]),
            value=handle, key="r%d" % r.key)

    # The native NavStack animates pushes/pops and the edge-swipe back; it reports a finished swipe here.
    return _NavContext.Provider(
        NavStack(*[route_view(r) for r in nav.stack], animated=animate, gesture=len(nav.stack) > 1,
                 on_pop_gesture=nav.go_back, style=[{"flex": 1, "overflow": "hidden"}, style]),
        value=Navigation(nav, top))


def _screen_pages(nav: _Nav, screens: Dict[str, Any], names: List[str], seen: set, cur: str, bg: str) -> List[Any]:
    pages = []
    for name in names:
        if name not in seen:
            continue
        handle = Navigation(nav, Route(0, name, {}))
        pages.append(_NavContext.Provider(
            View(_Screen(screen=screens[name], navigation=handle, params={}),
                 style=[_FILL, {"background_color": bg}, None if name == cur else _HIDDEN]),
            value=handle, key=name))
    return pages


@component
def Tabs(screens: Optional[Dict[str, Any]] = None, initial: Optional[str] = None,
         screen_options: Optional[Dict[str, Dict[str, Any]]] = None, tab_bar_style: Any = None,
         style: Any = None):
    """Bottom tab navigator (uses the `TabBar` widget). Tabs mount lazily on first visit and then stay mounted.
    `screen_options[name]` accepts `title`, `icon` (an `Icon` name) and `badge` (bool)."""
    from .widgets import TabBar
    c = use_theme()["colors"]
    screens = screens or {}
    opts = screen_options or {}
    names = list(screens)
    # Hooks before any early return: `screens` may toggle between empty and not.
    cur, set_cur = use_state(initial)
    seen = use_ref(set())
    holder = use_ref(None)
    parent = use_context(_NavContext)
    _, tick = use_state(0)
    if not names:
        return View(style=style)
    if cur not in screens:  # first render, or the current tab was removed
        cur = initial if initial in screens else names[0]
    seen.current.add(cur)
    if holder.current is None:
        holder.current = _TabNav(names, cur, tick)
    nav: _TabNav = holder.current
    nav.names, nav.parent = names, parent
    nav.select = set_cur
    pages = _screen_pages(nav, screens, names, seen.current, cur, c["background"])
    bar = TabBar(tabs=[{"key": n, "label": _title(n, opts.get(n, {})), "icon": opts.get(n, {}).get("icon", ""),
                        "badge": opts.get(n, {}).get("badge", False)} for n in names],
                 value=cur, on_change=set_cur, style=tab_bar_style)
    return _NavContext.Provider(
        View(View(*pages, style={"flex": 1}), bar, style=[{"flex": 1}, style]),
        value=Navigation(nav, Route(0, cur, {})))


@component
def TopTabs(screens: Optional[Dict[str, Any]] = None, initial: Optional[str] = None,
            screen_options: Optional[Dict[str, Dict[str, Any]]] = None, scrollable: Optional[bool] = None,
            tab_bar_style: Any = None, style: Any = None):
    """Top tab strip with an underline on the active tab. Scrolls horizontally when `scrollable` (default: more
    than 4 tabs). Tabs mount lazily on first visit. `screen_options[name]` accepts `title`."""
    from .ui import Pressable
    c = use_theme()["colors"]
    screens = screens or {}
    opts = screen_options or {}
    names = list(screens)
    cur, set_cur = use_state(initial)
    seen = use_ref(set())
    holder = use_ref(None)
    parent = use_context(_NavContext)
    _, tick = use_state(0)
    if not names:
        return View(style=style)
    if cur not in screens:
        cur = initial if initial in screens else names[0]
    seen.current.add(cur)
    if holder.current is None:
        holder.current = _TabNav(names, cur, tick)
    nav: _TabNav = holder.current
    nav.names, nav.parent = names, parent
    nav.select = set_cur
    scroll = len(names) > 4 if scrollable is None else scrollable
    items = []
    for name in names:
        on = name == cur
        col = c["primary"] if on else c["text_muted"]
        items.append(Pressable(
            Text(_title(name, opts.get(name, {})), number_of_lines=1,
                 style={"font_size": 14, "font_weight": "600" if on else "400", "color": col}),
            View(style={"position": "absolute", "left": 8, "right": 8, "bottom": 0, "height": 3,
                        "border_radius": 2, "background_color": c["primary"] if on else "#00000000"}),
            on_press=(lambda n=name: set_cur(n)), accessibility_role="tab", accessibility_state={"selected": on},
            key=name,
            style=[{"height": 46, "align_items": "center", "justify_content": "center"},
                   {"padding_horizontal": 16} if scroll else {"flex": 1}]))
    strip_style = [{"background_color": c["surface"], "border_bottom_width": 1, "border_color": c["border"]},
                   tab_bar_style]
    strip = (ScrollView(View(*items, style={"flex_direction": "row"}), horizontal=True, style=[strip_style, {"flex_grow": 0}])
             if scroll else View(*items, style=[{"flex_direction": "row"}, strip_style]))
    pages = _screen_pages(nav, screens, names, seen.current, cur, c["background"])
    return _NavContext.Provider(
        View(strip, View(*pages, style={"flex": 1}), style=[{"flex": 1}, style]),
        value=Navigation(nav, Route(0, cur, {})))


@component
def _DrawerList(names: Any = (), options: Any = None, current: str = "", title: str = "", on_select: Any = None):
    from .ui import Pressable
    from .widgets import Icon
    from .env import use_safe_area_insets
    c = use_theme()["colors"]
    top = use_safe_area_insets()["top"]
    opts = options or {}
    rows = []
    for n in names:
        on = n == current
        col = c["primary"] if on else c["text"]
        rows.append(Pressable(
            Icon(opts.get(n, {}).get("icon", ""), size=20, color=col) if opts.get(n, {}).get("icon") else None,
            Text(_title(n, opts.get(n, {})), style={"font_size": 15, "font_weight": "600" if on else "400",
                                                    "color": col, "margin_left": 14}),
            on_press=(lambda k=n: on_select(k)), key=n, accessibility_role="button",
            accessibility_state={"selected": on},
            style=[{"flex_direction": "row", "align_items": "center", "height": 48, "padding_horizontal": 16,
                    "margin_horizontal": 8, "margin_vertical": 2, "border_radius": 10},
                   {"background_color": c["surface_alt"]} if on else None]))
    return View(
        View(Text(title, style={"font_size": 20, "font_weight": "700", "color": c["text"]}),
             style={"padding": 20, "padding_top": 28 + top, "border_bottom_width": 1, "border_color": c["border"],
                    "margin_bottom": 8}) if title else None,
        ScrollView(*rows, style={"flex": 1}), style={"flex": 1, "padding_top": 0 if title else top})


@component
def Drawer(screens: Optional[Dict[str, Any]] = None, initial: Optional[str] = None,
           screen_options: Optional[Dict[str, Dict[str, Any]]] = None, drawer_content: Any = None,
           drawer_title: str = "", drawer_width: float = 300, header: bool = True, header_style: Any = None,
           title_style: Any = None, style: Any = None):
    """Side drawer navigator. Screens get a header with a menu button. Open with the button, a swipe from the left
    edge or `navigation.open_drawer()`; close by tapping/swiping the scrim, picking an item, or hardware back.
    `drawer_content(navigation=, current=, names=)` replaces the default item list.
    `screen_options[name]` accepts `title`, `icon`, `header` (bool) and `header_right`."""
    from .ui import Pressable
    from .widgets import Icon
    c = use_theme()["colors"]
    win = use_window_dimensions()
    screens = screens or {}
    opts = screen_options or {}
    names = list(screens)
    cur, set_cur = use_state(initial)
    is_open, set_open = use_state(False)
    shown, set_shown = use_state(False)  # panel + scrim mounted (stays true while the close animation runs)
    seen = use_ref(set())
    holder = use_ref(None)
    live = use_ref(None)
    locks = use_ref(set())
    _l, bump_lock = use_state(0)

    def lock_edge(token: Any, on: bool) -> None:
        if (token in locks.current) != on:
            (locks.current.add if on else locks.current.discard)(token)
            bump_lock(lambda v: v + 1)
    lock_edge_ref = use_ref(None)
    if lock_edge_ref.current is None:
        lock_edge_ref.current = lock_edge
    parent = use_context(_NavContext)
    _, tick = use_state(0)
    p = use_animated_value(0.0)
    width = min(float(drawer_width), win["width"] * 0.82)
    tx, scrim_op = use_memo(lambda: (p.interpolate([0, 1], [-width, 0]), p.interpolate([0, 1], [0, 0.5])), [width])

    def set_open_(v: bool) -> None:
        if v:
            set_shown(True)
        set_open(v)
    live.current = is_open

    def animate() -> None:
        if is_open:
            Animated.timing(p, 1, 260, Easing.out(Easing.cubic)).start()
        elif shown:
            Animated.timing(p, 0, 200, Easing.in_(Easing.cubic)).start(
                lambda r: None if live.current else set_shown(False))
    use_effect(animate, [is_open])
    _use_back(lambda: bool(live.current) and (set_open(False) or True))

    def edge_end(g: Any) -> None:
        if g.dx > 50 or g.vx > 500:
            set_open_(True)

    def scrim_end(g: Any) -> None:
        if abs(g.dx) < 8 or g.dx < -50 or g.vx < -500:
            set_open(False)
    edge = use_pan_responder(on_end=edge_end)
    scrim_pan = use_pan_responder(on_end=scrim_end)
    if not names:
        return View(style=style)
    if cur not in screens:
        cur = initial if initial in screens else names[0]
    seen.current.add(cur)
    if holder.current is None:
        holder.current = _DrawerNav(names, cur, tick)
    nav: _DrawerNav = holder.current
    nav.names, nav.parent = names, parent
    nav.select, nav.is_open, nav.set_open = set_cur, is_open, set_open_
    handle = Navigation(nav, Route(0, cur, {}))
    o = opts.get(cur, {})
    pages = _screen_pages(nav, screens, names, seen.current, cur, c["background"])
    menu = Pressable(Icon("menu", size=22, color=c["text"]), on_press=lambda: set_open_(True),
                     accessibility_label="Menu",
                     style={"width": 40, "height": 40, "align_items": "center", "justify_content": "center"})
    main = View(
        _Header(title=_title(cur, o), left=menu, header_style=header_style, title_style=title_style,
                right=o.get("header_right")) if header and o.get("header", True) else None,
        View(_TopInset.Provider(*pages, value=not (header and o.get("header", True))), style={"flex": 1}),
        style={"flex": 1})
    layers = [main]
    if shown:
        content = (drawer_content(navigation=handle, current=cur, names=names) if drawer_content is not None
                   else _DrawerList(names=names, options=opts, current=cur, title=drawer_title,
                                    on_select=lambda n: (set_cur(n), set_open(False))))
        layers.append(View(View(style={"flex": 1, "background_color": "#000000", "opacity": scrim_op}),
                           key="scrim", style=_FILL, **scrim_pan))
        layers.append(View(content, key="panel",
                           style={"position": "absolute", "left": 0, "top": 0, "bottom": 0, "width": width,
                                  "background_color": c["surface"], "translate_x": tx, "shadow_color": "#000000",
                                  "shadow_opacity": 0.3, "shadow_radius": 12, "elevation": 16}))
    elif not locks.current:
        layers.append(View(key="edge", style={"position": "absolute", "left": 0, "top": 0, "bottom": 0, "width": 16},
                           **edge))
    return _NavContext.Provider(_EdgeLock.Provider(View(*layers, style=[{"flex": 1, "overflow": "hidden"}, style]),
                                                   value=lock_edge_ref.current), value=handle)
