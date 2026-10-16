"""Per-app router runtime: the Store, dynamic screen options and the contexts layouts and routes read."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from ..hooks import create_context
from .store import Node, Store


def same(a: Any, b: Any) -> bool:
    """Equality for option dicts where closures are rebuilt every render: functions match by code and captured values."""
    if callable(a) and callable(b) and hasattr(a, "__code__") and hasattr(b, "__code__"):
        ca = tuple(c.cell_contents for c in (a.__closure__ or ()))
        cb = tuple(c.cell_contents for c in (b.__closure__ or ()))
        return a.__code__ is b.__code__ and same(ca, cb)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a is b or a == b


class Runtime:
    def __init__(self, store: Store, root_dir: str) -> None:
        self.store = store
        self.root_dir = root_dir
        self.options: Dict[str, Dict[str, Any]] = {}  # route key -> options set with setOptions / <Stack.Screen>
        self.resolved: Dict[str, Dict[str, Any]] = {}  # route key -> merged options from the last navigator render
        self.on_change: Callable[[], None] = lambda: None

    def set_options(self, route_key: str, options: Optional[Dict[str, Any]]) -> None:
        if options:
            if same(self.options.get(route_key), options):
                return
            self.options[route_key] = dict(options)
        elif self.options.pop(route_key, None) is None:
            return
        self.on_change()

    def node(self, key: str) -> Optional[Node]:
        return find_node(self.store.state, key)


def find_node(node: Optional[Node], key: str) -> Optional[Node]:
    if node is None:
        return None
    if node["key"] == key:
        return node
    for r in node["routes"]:
        hit = find_node(r.get("state"), key)
        if hit is not None:
            return hit
    return None


RuntimeContext = create_context(None)
# {"nav": Navigator, "key": node key} for the layout being rendered
NavigatorContext = create_context(None)
# {"key": route key, "name": route name, "node_key": owning navigator node key, "nav": Navigator}
RouteContext = create_context(None)
