from ...component import component
from ..screen import route_element, use_navigator


@component
def Slot(*children):
    """Renders the focused child route (no chrome)."""
    _, nav, node, _ = use_navigator("slot", children, None)
    return route_element(nav, node, node["routes"][node["index"]])
