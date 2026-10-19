"""Text: styled string host with nested-Text spans. Nested `Text` children inherit the parent's text style."""
from __future__ import annotations

from typing import Any, Dict, List

from .._keys import alias_props, needs_alias
from ..element import Element, _SCALARS, _join_text
from ..style import normalize_shared


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
            own = normalize_shared(c.props.get("style"))
            st.update({k: v for k, v in own.items() if k in _TEXT_STYLE_KEYS})
            if "text" in c.props:
                spans.append({"text": _transform(str(c.props["text"]), st.get("text_transform")), "style": st})
            for cc in c.children:
                _text_spans([cc], st, spans)
        else:
            raise TypeError("Text children must be str/int/float or Text, got %s" % type(c).__name__)


def Text(*children: Any, key: Any = None, **props: Any) -> Element:
    if needs_alias(props):
        props = alias_props(props)
    if "number_of_lines" in props or "allow_font_scaling" in props:  # native reads these from style
        extra = {k: props.pop(k) for k in ("number_of_lines", "allow_font_scaling") if k in props}
        props["style"] = [props.get("style"), extra]
    single = len(children) == 1 and children[0].__class__ is str  # Text("label"): skip the generic walk
    nested = not single and _has_element(children)
    base = normalize_shared(props.get("style"))
    mode = base.get("text_transform")
    if not nested:
        text = children[0] if single else _join_text(children)
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
    for c in seq:
        if isinstance(c, Element) or (isinstance(c, (list, tuple)) and _has_element(c)):
            return True
    return False
