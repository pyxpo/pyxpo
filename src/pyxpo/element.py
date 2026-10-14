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


def _transform(text: str, mode: Any) -> str:
    if mode == "uppercase":
        return text.upper()
    if mode == "lowercase":
        return text.lower()
    if mode == "capitalize":
        return " ".join(w[:1].upper() + w[1:] for w in text.split(" "))
    return text


_TEXT_STYLE_KEYS = ("color", "background_color", "font_size", "font_weight", "font_style", "font_family",
                    "font_file", "letter_spacing", "text_decoration", "text_transform",
                    "text_shadow_color", "text_shadow_offset_x", "text_shadow_offset_y", "text_shadow_radius")


def _text_spans(children: Any, inherited: Dict[str, Any], spans: List[Dict[str, Any]]) -> None:
    """Flatten Text children into spans [{text, style}] where style is the full inherited text style."""
    from .style import normalize
    for c in children:
        if c is None or isinstance(c, bool):
            continue
        if isinstance(c, (list, tuple)):
            _text_spans(c, inherited, spans)
        elif isinstance(c, _SCALARS):
            spans.append({"text": _transform(str(c), inherited.get("text_transform")), "style": dict(inherited)})
        elif isinstance(c, Element) and c.type == "Text":
            if "spans" in c.props:  # child already built its own spans: re-base them on our inherited style
                for sp in c.props["spans"]:
                    st = dict(inherited)
                    st.update(sp["style"])
                    spans.append({"text": _transform(sp["text"], st.get("text_transform")), "style": st})
                continue
            st = dict(inherited)
            own = normalize(c.props.get("style"))
            st.update({k: v for k, v in own.items() if k in _TEXT_STYLE_KEYS})
            if "text" in c.props:
                spans.append({"text": _transform(str(c.props["text"]), st.get("text_transform")), "style": st})
            for cc in c.children:
                _text_spans([cc], st, spans)
        else:
            raise TypeError("Text children must be str/int/float or Text, got %s" % type(c).__name__)


def _text_factory(*children: Any, key: Any = None, **props: Any) -> Element:
    from .style import normalize
    nested = any(isinstance(c, Element) or (isinstance(c, (list, tuple)) and _has_element(c)) for c in children)
    base = normalize(props.get("style"))
    mode = base.get("text_transform")
    if not nested:
        text = _join_text(children)
        if text or "text" not in props:
            props["text"] = text
        if "text" in props and mode:
            props["text"] = _transform(str(props["text"]), mode)
        return Element("Text", props, [], key)
    spans: List[Dict[str, Any]] = []
    _text_spans(children, {k: v for k, v in base.items() if k in _TEXT_STYLE_KEYS and k != "background_color"}, spans)
    props["text"] = "".join(sp["text"] for sp in spans)
    props["spans"] = spans
    return Element("Text", props, [], key)


def _has_element(seq: Any) -> bool:
    return any(isinstance(c, Element) or (isinstance(c, (list, tuple)) and _has_element(c)) for c in seq)


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


def ScrollView(*children: Any, key: Any = None, **props: Any) -> Element:
    """Scrollable container. `content_container_style` styles the inner content box."""
    kids = flatten(children)
    ccs = props.pop("content_container_style", None)
    if ccs is not None:
        kids = [Element("View", {"style": [{"flex_direction": "row"}, ccs] if props.get("horizontal") else ccs}, kids)]
    return Element("ScrollView", props, kids, key)


def Path(*children: Any, key: Any = None, d: Any = None, stroke: Any = None, fill: Any = None, stroke_width: float = 2,
         viewbox: float = 24, **props: Any) -> Element:
    """Vector shape. `d` is SVG path data (str) or commands from `icons.parse_path`; drawn scaled from a
    `viewbox` x `viewbox` square to the view size (set width/height in `style`)."""
    from .icons import parse_path
    from .style import parse_color
    props["path"] = parse_path(d) if isinstance(d, str) else (d or [])
    props["viewbox"] = float(viewbox)
    props["stroke_width"] = float(stroke_width)
    if stroke is not None:
        props["stroke"] = parse_color(stroke)
    if fill is not None:
        props["fill"] = parse_color(fill)
    return Element("Path", props, [], key)


def Image(*children: Any, key: Any = None, **props: Any) -> Element:
    """Image from `source`: a path, an http(s) URL, a data: URI, `asset:name`, or `{"uri": ...}`."""
    src = props.get("source")
    if isinstance(src, str):
        src = {"uri": src}
    if isinstance(src, dict) and isinstance(src.get("uri"), str):
        uri = src["uri"]
        if "://" not in uri and not uri.startswith(("data:", "asset:", "/")):
            import os
            uri = os.path.abspath(uri)
        src = dict(src, uri=uri)
    if src is not None:
        props["source"] = src
    return Element("Image", props, [], key)


View = _host("View")
_Modal = _host("Modal")
Text = _text_factory
Text.__name__ = "Text"
Button = _host("Button", "text")
TextInput = _host("TextInput")
