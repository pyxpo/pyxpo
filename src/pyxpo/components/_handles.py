"""What `ref.current` is for a mounted host view: the imperative half of the RN component API."""
from __future__ import annotations

from typing import Any, Dict, Optional

from .._keys import snake_aliases
from ..apis._bridge import call


class ViewHandle:
    def __init__(self, node_id: int) -> None:
        self._id = node_id


def _opts(options: Optional[Dict[str, Any]], kw: Dict[str, Any]) -> Dict[str, Any]:
    return {**(options or {}), **kw}


@snake_aliases
class ScrollViewHandle(ViewHandle):
    def scrollTo(self, options: Optional[Dict[str, Any]] = None, **kw: Any) -> None:
        """`scrollTo({"x": 0, "y": 100, "animated": True})` or `scrollTo(y=100)`."""
        o = _opts(options, kw)
        call("Scroll", "to", self._id, float(o.get("x", 0)), float(o.get("y", 0)), bool(o.get("animated", True)))

    def scrollToEnd(self, options: Optional[Dict[str, Any]] = None, **kw: Any) -> None:
        call("Scroll", "to_end", self._id, bool(_opts(options, kw).get("animated", True)))

    def flashScrollIndicators(self) -> None:
        return None


@snake_aliases
class TextInputHandle(ViewHandle):
    def focus(self) -> None:
        call("TextInput", "focus", self._id)

    def blur(self) -> None:
        call("TextInput", "blur", self._id)

    def clear(self) -> None:
        call("TextInput", "clear", self._id)

    def setSelection(self, start: int, end: int) -> None:
        call("TextInput", "set_selection", self._id, int(start), int(end))


def make_handle(host: Any, node_id: int) -> ViewHandle:
    if host == "ScrollView":
        return ScrollViewHandle(node_id)
    if host == "TextInput":
        return TextInputHandle(node_id)
    return ViewHandle(node_id)
