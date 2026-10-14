from __future__ import annotations

from typing import Any, Dict, List, Optional


class Element:
    """Immutable-by-convention description of a UI node. `type` is a host name (str) or a Component."""

    __slots__ = ("type", "props", "children", "key")

    def __init__(self, type: Any, props: Optional[Dict[str, Any]] = None,
                 children: Optional[List["Element"]] = None, key: Any = None) -> None:
        self.type = type
        self.props = props or {}
        self.children = children or []
        self.key = key

    def __repr__(self) -> str:
        name = self.type if isinstance(self.type, str) else getattr(self.type, "name", self.type)
        return "Element(%s, props=%r, children=%d, key=%r)" % (name, self.props, len(self.children), self.key)


_SCALARS = (str, int, float)


def flatten(children: Any) -> List[Element]:
    """Flatten nested lists, drop None/bool, turn bare scalars into Text elements."""
    out: List[Element] = []
    for c in children:
        if c is None or isinstance(c, bool):
            continue
        if isinstance(c, (list, tuple)):
            out.extend(flatten(c))
        elif isinstance(c, Element):
            out.append(c)
        elif isinstance(c, _SCALARS):
            out.append(Element("Text", {"text": str(c)}))
        else:
            raise TypeError("invalid child of type %s" % type(c).__name__)
    return out


def _join_text(children: Any) -> str:
    parts: List[str] = []
    for c in children:
        if c is None or isinstance(c, bool):
            continue
        if isinstance(c, (list, tuple)):
            parts.append(_join_text(c))
        elif isinstance(c, _SCALARS):
            parts.append(str(c))
        else:
            raise TypeError("text children must be str/int/float, got %s" % type(c).__name__)
    return "".join(parts)


def _host(name: str, text_prop: Optional[str] = None):
    def factory(*children: Any, key: Any = None, **props: Any) -> Element:
        if text_prop:
            text = _join_text(children)
            if text or text_prop not in props:
                props[text_prop] = text
            return Element(name, props, [], key)
        return Element(name, props, flatten(children), key)

    factory.__name__ = name
    return factory


View = _host("View")
ScrollView = _host("ScrollView")
Text = _host("Text", "text")
Button = _host("Button", "text")
Image = _host("Image")
TextInput = _host("TextInput")
