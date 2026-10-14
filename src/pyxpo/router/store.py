"""Navigation state of pyxpo.router (expo-router / react-navigation semantics), pure Python.

State is a tree of navigator nodes::

    {"key": "nav-3", "type": "stack"|"tabs"|"drawer"|"slot", "index": i,
     "routes": [{"key": "home-4", "name": "home", "params": {...}, "state": <node>?}, ...],
     "drawer_open": False}                      # drawer nodes only

The root node belongs to `tree.root`; a route whose screen is a nested navigator carries that navigator's node in
`state` (unfocused tab/drawer routes get it lazily, when first focused). Every change builds a new tree (copy on write)
and commits only when it differs, so repeated navigation is a no-op and subscribers see immutable snapshots.

Navigator types. A navigator's type is only known when its `_layout` renders `Stack`/`Tabs`/`Drawer`/`Slot`, so the
layout calls `register_navigator(nav.path, type, options)` on render. Nodes of a navigator that is not registered yet
are built as stacks (a missing root `_layout.py` is pre-registered as "slot"). The first registration reconciles every
existing node of that navigator: a stack becomes tabs/drawer with one route per screen and `index` on the route that
was focused (so a deep link into a tab keeps that tab), and a stack gets `initialRouteName` inserted below its target.
Later registrations that change type or options re-shape existing nodes the same way (hot reload). Options read:
`initialRouteName` (overrides `unstable_settings` passed in via `initial_route_names`) and `order` (screen names in
declaration order; tabs/drawer routes follow it, undeclared screens after, `index` first).

Actions apply at the first level where the current focused chain diverges from the matched chain:
stack  push appends; navigate keeps an identical top, else pops to (and re-params) the nearest same-name route,
       else appends; replace swaps the top; dismiss_to is navigate that replaces instead of appending.
tabs / drawer  every action jumps to the tab (and closes the drawer).
slot   one route; a different screen replaces it.
back() closes an open drawer, else lets the deepest focused navigator handle it: a stack pops, a tab/drawer that is
not on its first route goes there ("firstRoute"); returns False when nothing handled it (the app may exit).
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple
from urllib.parse import quote

from .discovery import Navigator, RouteTree, Screen
from .matching import Href, Match, match

Node = Dict[str, Any]
RouteState = Dict[str, Any]
TYPES = ("stack", "tabs", "drawer", "slot")
_TABBED = ("tabs", "drawer")


def _strs(v: Any) -> Any:
    return [str(x) for x in v] if isinstance(v, (list, tuple)) else str(v)


class Store:
    def __init__(self, tree: RouteTree, initial_href: Href = "/",
                 initial_route_names: Optional[Callable[[Navigator], Optional[str]]] = None) -> None:
        self.tree = tree
        self._initial_names = initial_route_names or (lambda nav: None)
        self._types: Dict[str, str] = {}
        self._options: Dict[str, Dict[str, Any]] = {}
        if tree.root.layout_file is None:
            self._types[tree.root.path] = "slot"
        self._n = 0
        self._subs: List[Callable[[], None]] = []
        self._listeners: Dict[Tuple[str, str], List[Callable[[], None]]] = {}
        self._depth = 0
        self._dirty = False
        self._nf = Screen("+not-found", (), None, None, not_found=True)
        self._nf.parent = tree.root
        chain, levels = self._levels(match(tree, initial_href))
        self._state: Node = self._node(tree.root, chain, levels)
        self._focused = self._focus_keys(self._state)
        self._notified = self._state

    # ---- subscription -------------------------------------------------------------------------------------------
    @property
    def state(self) -> Node:
        """Current state tree; treat as read-only (it is replaced, never mutated, on change)."""
        return self._state

    def subscribe(self, fn: Callable[[], None]) -> Callable[[], None]:
        self._subs.append(fn)
        return lambda: fn in self._subs and self._subs.remove(fn)

    def add_listener(self, route_key: str, event: str, fn: Callable[[], None]) -> Callable[[], None]:
        """`event` 'focus' | 'blur' for one route key, emitted after subscribers are notified of the change."""
        fns = self._listeners.setdefault((route_key, event), [])
        fns.append(fn)
        return lambda: fn in fns and fns.remove(fn)

    @contextmanager
    def batch(self) -> Iterator[None]:
        """Notify subscribers (and emit focus/blur) once for all changes made inside the block."""
        self._depth += 1
        try:
            yield
        finally:
            self._depth -= 1
            if not self._depth and self._dirty:
                self._flush()

    def _mutate(self, fn: Callable[[Node], Any]) -> Any:
        new = copy.deepcopy(self._state)
        out = fn(new)
        if new != self._state:
            self._state = new
            self._dirty = True
            if not self._depth:
                self._flush()
        return out

    def _flush(self) -> None:
        self._dirty = False
        if self._state == self._notified:       # a batch that ended where it started
            return
        self._notified = self._state
        old, self._focused = self._focused, self._focus_keys(self._state)
        for fn in list(self._subs):
            fn()
        events = [(k, "blur") for k in reversed(old) if k not in self._focused]
        events += [(k, "focus") for k in self._focused if k not in old]
        for k, ev in events:
            for fn in list(self._listeners.get((k, ev), ())):
                fn()

    # ---- navigator registration ---------------------------------------------------------------------------------
    def register_navigator(self, nav_id: str, type: str, options: Optional[Dict[str, Any]] = None) -> None:
        """Called by a layout on render with its Navigator.path; reconciles nodes built before the type was known."""
        if type not in TYPES:
            raise ValueError("unknown navigator type %r" % type)
        options = dict(options or {})
        if self._types.get(nav_id) == type and self._options.get(nav_id, {}) == options:
            return
        first = nav_id not in self._types
        self._types[nav_id] = type
        self._options[nav_id] = options

        def fn(s: Node) -> None:
            for node, nav in [x for x in self._walk(s, self.tree.root) if x[1].path == nav_id]:
                self._conform(node, nav, first)
        self._mutate(fn)

    def set_tree(self, tree: RouteTree) -> None:
        """Swap in a re-discovered tree (hot reload) keeping navigation state; routes whose screen vanished render
        not-found, routes that stopped (or started) being a navigator drop (or get) their nested state."""
        self.tree = tree
        self._nf.parent = tree.root
        if tree.root.layout_file is None:
            self._types[tree.root.path] = "slot"
        self._mutate(lambda s: self._fit(s, tree.root))

    def _fit(self, node: Node, nav: Navigator) -> None:
        for i, r in enumerate(node["routes"]):
            sub = self._screen(nav, r["name"]).navigator
            if sub is None:
                r.pop("state", None)
            elif "state" in r:
                self._fit(r["state"], sub)
            elif i == node["index"]:
                r["state"] = self._node(sub, [], [])

    def _conform(self, node: Node, nav: Navigator, first: bool) -> None:
        t = self._types[nav.path]
        focused = node["routes"][node["index"]]
        if t in _TABBED:
            node["routes"], node["index"] = self._tab_routes(nav, node["routes"], focused)
        elif t == "slot" or node["type"] != "stack":
            node["routes"], node["index"] = [focused], 0
        if t == "stack" and first:
            self._add_initial(node, nav)
        self._set_type(node, t)

    # ---- actions --------------------------------------------------------------------------------------------------
    def navigate(self, href: Href) -> None:
        self._go(href, "navigate")

    def push(self, href: Href) -> None:
        self._go(href, "push")

    def replace(self, href: Href) -> None:
        self._go(href, "replace")

    def dismiss_to(self, href: Href) -> None:
        self._go(href, "pop_to")

    def back(self) -> bool:
        """Go back one step; False when nothing can go back (caller may exit the app)."""
        return self._mutate(self._back)

    def can_go_back(self) -> bool:
        return self._back(copy.deepcopy(self._state))

    def dismiss(self, n: int = 1) -> None:
        """Pop `n` routes (at most down to its first) from the nearest focused stack that has more than one."""
        self._mutate(lambda s: self._pop_nearest(s, n))

    def dismiss_all(self) -> None:
        self._mutate(lambda s: self._pop_nearest(s, None))

    def can_dismiss(self) -> bool:
        return self._nearest_stack(self._state) is not None

    def set_params(self, params: Dict[str, Any], route_key: Optional[str] = None) -> None:
        """Merge `params` into a route's params (focused route by default); a None value removes the key."""
        def fn(s: Node) -> None:
            if route_key is None:
                route = self._chain(s)[-1][2]
            else:
                found = self._find(s, route_key)
                if found is None:
                    return
                route = found[2]
            for k, v in params.items():
                if v is None:
                    route["params"].pop(k, None)
                else:
                    route["params"][k] = _strs(v)
        self._mutate(fn)

    def pop(self, route_key: str) -> None:
        """Remove `route_key` and everything above it from its stack (pop gesture / header back of that route)."""
        def fn(s: Node) -> None:
            found = self._find(s, route_key)
            if found and found[0]["type"] == "stack":
                node, i = found[0], found[0]["routes"].index(found[2])
                if i:
                    del node["routes"][i:]
                    node["index"] = i - 1
        self._mutate(fn)

    def set_index(self, nav_key: str, index: int) -> None:
        """Focus route `index` of the tabs/drawer node `nav_key` (tab press / drawer item)."""
        def fn(s: Node) -> None:
            for node, nav in self._walk(s, self.tree.root):
                if node["key"] == nav_key and node["type"] in _TABBED and 0 <= index < len(node["routes"]):
                    self._focus(node, nav, index)
                    return
        self._mutate(fn)

    def set_drawer_open(self, nav_key: str, open: bool) -> None:
        def fn(s: Node) -> None:
            for node, _ in self._walk(s, self.tree.root):
                if node["key"] == nav_key and node["type"] == "drawer":
                    node["drawer_open"] = bool(open)
        self._mutate(fn)

    # ---- read helpers ---------------------------------------------------------------------------------------------
    def focused_chain(self) -> List[Tuple[Node, RouteState]]:
        """(navigator node, focused route) pairs from the root to the focused leaf."""
        return [(node, route) for node, _, route, _ in self._chain(self._state)]

    @property
    def pathname(self) -> str:
        chain = self._chain(self._state)
        params = chain[-1][2]["params"]
        if chain[-1][3].not_found:
            return "/" + "/".join(params.get("+not-found", []))
        parts: List[str] = []
        for *_, scr in chain:
            for kind, val in scr.segments:
                if kind == "s":
                    parts.append(val)
                else:
                    v = params.get(val, [] if kind == "c" else "")
                    parts += [quote(x, safe="") for x in (v if isinstance(v, list) else [v])]
        return "/" + "/".join(p for p in parts if p)

    @property
    def segments(self) -> List[str]:
        """Focused route names split into segments, groups and dynamic brackets kept, `index` dropped."""
        return [p for _, _, route, _ in self._chain(self._state) for p in route["name"].split("/") if p != "index"]

    @property
    def params(self) -> Dict[str, Any]:
        """Focused route's params (path params and query; str or list of str)."""
        return dict(self._chain(self._state)[-1][2]["params"])

    def route_params(self, route_key: str) -> Dict[str, Any]:
        found = self._find(self._state, route_key)
        return dict(found[2]["params"]) if found else {}

    def is_focused(self, route_key: str) -> bool:
        return route_key in self._focused

    # ---- internals ------------------------------------------------------------------------------------------------
    def _key(self, name: str) -> str:
        self._n += 1
        return "%s-%d" % (name, self._n)

    def _go(self, href: Href, action: str) -> None:
        chain, levels = self._levels(match(self.tree, href, current=self.pathname))
        self._mutate(lambda s: self._apply(s, chain, levels, action))

    def _levels(self, m: Match) -> Tuple[List[Screen], List[Dict[str, Any]]]:
        """Matched chain (built-in not-found when empty) and each level's params: a layout route gets the path params
        of its own segments, the leaf gets all params plus the query."""
        chain = m.chain or [self._nf]
        names: set = set()
        levels = []
        for i, scr in enumerate(chain):
            names.update(v for k, v in scr.segments if k != "s")
            levels.append(m.all_params if i == len(chain) - 1 else {k: v for k, v in m.params.items() if k in names})
        return chain, levels

    def _apply(self, node: Node, chain: List[Screen], levels: List[Dict[str, Any]], action: str) -> None:
        for i, scr in enumerate(chain):
            last = i == len(chain) - 1
            p, rest, rp = levels[i], chain[i + 1:], levels[i + 1:]
            routes = node["routes"]
            if node["type"] == "stack":
                top, j = routes[-1], None
                if top["name"] == scr.name and top["params"] == p and not (last and action in ("push", "replace")):
                    j = len(routes) - 1
                elif action in ("navigate", "pop_to"):
                    j = next((j for j in range(len(routes) - 1, -1, -1) if routes[j]["name"] == scr.name), None)
                if j is None:
                    new = self._route(scr, p, rest, rp)
                    if action in ("push", "navigate"):
                        routes.append(new)
                    else:
                        routes[-1] = new
                    node["index"] = len(routes) - 1
                    return
                del routes[j + 1:]
                route = routes[j]
                route["params"] = dict(p)
                node["index"] = j
            elif node["type"] == "slot":
                route = routes[0]
                if route["name"] != scr.name:
                    node["routes"] = [self._route(scr, p, rest, rp)]
                    return
                route["params"] = dict(p)
            else:
                j = next((j for j, r in enumerate(routes) if r["name"] == scr.name), None)
                if j is None:
                    routes.append({"key": self._key(scr.name), "name": scr.name, "params": {}})
                    j = len(routes) - 1
                node["index"] = j
                if node["type"] == "drawer":
                    node["drawer_open"] = False
                route = routes[j]
                route["params"] = dict(p)
            if last:
                return
            if "state" not in route:
                route["state"] = self._node(scr.navigator, rest, rp)
                return
            node = route["state"]

    def _route(self, scr: Screen, params: Dict[str, Any], rest: List[Screen], rp: List[Dict[str, Any]]) -> RouteState:
        r: RouteState = {"key": self._key(scr.name), "name": scr.name, "params": dict(params)}
        if scr.navigator is not None:
            r["state"] = self._node(scr.navigator, rest, rp)
        return r

    def _node(self, nav: Navigator, rest: List[Screen], rp: List[Dict[str, Any]]) -> Node:
        """New node for `nav` focused on rest[0] (or its initial screen when `rest` is empty)."""
        t = self._types.get(nav.path, "stack")
        leaf = self._route(rest[0], rp[0], rest[1:], rp[1:]) if rest else self._route(self._default(nav), {}, [], [])
        node: Node = {"key": self._key("nav"), "type": t, "routes": [leaf], "index": 0}
        if t in _TABBED:
            node["routes"], node["index"] = self._tab_routes(nav, [leaf], leaf)
        elif t == "stack":
            self._add_initial(node, nav)
        self._set_type(node, t)
        return node

    def _set_type(self, node: Node, t: str) -> None:
        node["type"] = t
        if t == "drawer":
            node.setdefault("drawer_open", False)
        else:
            node.pop("drawer_open", None)

    def _initial(self, nav: Navigator) -> Optional[str]:
        return self._options.get(nav.path, {}).get("initialRouteName") or self._initial_names(nav)

    def _add_initial(self, node: Node, nav: Navigator) -> None:
        name = self._initial(nav)
        scr = nav.screen(name) if name else None
        if scr is not None and node["routes"][0]["name"] != name:
            node["routes"].insert(0, self._route(scr, {}, [], []))
        node["index"] = len(node["routes"]) - 1

    def _ordered(self, nav: Navigator) -> List[Screen]:
        rank = {n: i for i, n in enumerate(self._options.get(nav.path, {}).get("order") or [])}
        return sorted((s for s in nav.screens if not s.not_found),
                      key=lambda s: (rank.get(s.name, len(rank)), s.name != "index"))

    def _default(self, nav: Navigator) -> Screen:
        name = self._initial(nav)
        return (nav.screen(name) if name else None) or self._ordered(nav)[0]

    def _tab_routes(self, nav: Navigator, existing: List[RouteState],
                    focused: RouteState) -> Tuple[List[RouteState], int]:
        """One route per screen in tab order, reusing `existing` routes by name; index of `focused`."""
        by_name = {r["name"]: r for r in existing}
        by_name[focused["name"]] = focused
        routes = [by_name.get(s.name) or {"key": self._key(s.name), "name": s.name, "params": {}}
                  for s in self._ordered(nav)]
        if focused not in routes:
            routes.append(focused)
        return routes, next(i for i, r in enumerate(routes) if r is focused)

    def _focus(self, node: Node, nav: Navigator, index: int) -> None:
        node["index"] = index
        if node["type"] == "drawer":
            node["drawer_open"] = False
        route = node["routes"][index]
        scr = self._screen(nav, route["name"])
        if scr.navigator is not None and "state" not in route:
            route["state"] = self._node(scr.navigator, [], [])

    def _screen(self, nav: Navigator, name: str) -> Screen:
        return nav.screen(name) or self._nf

    def _walk(self, node: Node, nav: Navigator) -> Iterator[Tuple[Node, Navigator]]:
        yield node, nav
        for r in node["routes"]:
            if "state" in r:
                yield from self._walk(r["state"], self._screen(nav, r["name"]).navigator)

    def _find(self, s: Node, route_key: str) -> Optional[Tuple[Node, Navigator, RouteState]]:
        for node, nav in self._walk(s, self.tree.root):
            for r in node["routes"]:
                if r["key"] == route_key:
                    return node, nav, r
        return None

    def _chain(self, s: Node) -> List[Tuple[Node, Navigator, RouteState, Screen]]:
        """Focused path: (node, its navigator, focused route, that route's screen) from the root down."""
        out = []
        node: Optional[Node] = s
        nav: Optional[Navigator] = self.tree.root
        while node is not None and nav is not None:
            route = node["routes"][node["index"]]
            scr = self._screen(nav, route["name"])
            out.append((node, nav, route, scr))
            node, nav = route.get("state"), scr.navigator
        return out

    def _focus_keys(self, s: Node) -> List[str]:
        return [route["key"] for _, _, route, _ in self._chain(s)]

    def _back(self, s: Node) -> bool:
        chain = self._chain(s)
        for node, *_ in reversed(chain):
            if node.get("drawer_open"):
                node["drawer_open"] = False
                return True
        for node, nav, _, _ in reversed(chain):
            if node["type"] == "stack" and len(node["routes"]) > 1:
                node["routes"].pop()
                node["index"] = len(node["routes"]) - 1
                return True
            if node["type"] in _TABBED and node["index"]:
                self._focus(node, nav, 0)
                return True
        return False

    def _nearest_stack(self, s: Node) -> Optional[Node]:
        for node, *_ in reversed(self._chain(s)):
            if node["type"] == "stack" and len(node["routes"]) > 1:
                return node
        return None

    def _pop_nearest(self, s: Node, n: Optional[int]) -> None:
        node = self._nearest_stack(s)
        if node is not None:
            keep = 1 if n is None else max(1, len(node["routes"]) - n)
            del node["routes"][keep:]
            node["index"] = keep - 1
