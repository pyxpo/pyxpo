"""Style handling: StyleSheet, style flattening, shorthand expansion, color parsing.

Sizes are dp (Android) / pt (iOS). Native code converts with the screen density.
"""
from __future__ import annotations

import re
import sys
from typing import Any, Dict, List

# shorthand -> the longhand keys it expands to (in order)
_EDGES = ("top", "right", "bottom", "left")
_EDGE_FAMILIES = ("margin", "padding")
_CORNERS = ("top_left", "top_right", "bottom_right", "bottom_left")

# every key the layout/painter understands; unknown keys warn in dev
KNOWN_KEYS = frozenset("""
display position top right bottom left start end z_index overflow
width height min_width min_height max_width max_height aspect_ratio
flex flex_grow flex_shrink flex_basis flex_direction flex_wrap
justify_content align_items align_self align_content gap row_gap column_gap
margin margin_top margin_right margin_bottom margin_left margin_horizontal margin_vertical
padding padding_top padding_right padding_bottom padding_left padding_horizontal padding_vertical
border_width border_top_width border_right_width border_bottom_width border_left_width
border_color border_top_color border_right_color border_bottom_color border_left_color
border_radius border_top_left_radius border_top_right_radius border_bottom_right_radius border_bottom_left_radius
background_color linear_gradient opacity
shadow_color shadow_offset_x shadow_offset_y shadow_radius shadow_opacity elevation
transform rotate scale scale_x scale_y translate_x translate_y
color font_size font_weight font_style font_family line_height letter_spacing text_align
text_decoration text_transform number_of_lines allow_font_scaling
text_shadow_color text_shadow_offset_x text_shadow_offset_y text_shadow_radius
""".split())

NAMED_COLORS: Dict[str, int] = {
    "transparent": 0x00000000, "black": 0xFF000000, "white": 0xFFFFFFFF, "red": 0xFFFF0000,
    "green": 0xFF008000, "blue": 0xFF0000FF, "yellow": 0xFFFFFF00, "cyan": 0xFF00FFFF,
    "magenta": 0xFFFF00FF, "gray": 0xFF808080, "grey": 0xFF808080, "orange": 0xFFFFA500,
    "purple": 0xFF800080, "pink": 0xFFFFC0CB, "brown": 0xFFA52A2A, "lime": 0xFF00FF00,
    "navy": 0xFF000080, "teal": 0xFF008080, "silver": 0xFFC0C0C0, "maroon": 0xFF800000,
}

_RGB = re.compile(r"^(rgba?)\(\s*([^)]*)\)$", re.I)


class StyleError(ValueError):
    pass


_COLORS: Dict[str, int] = {}
_NORMALIZED: Dict[Any, Dict[str, Any]] = {}


def clear_cache() -> None:
    _NORMALIZED.clear()


def parse_color(value: Any) -> int:
    """Return color as 0xAARRGGBB int. Accepts int, #rgb, #rgba, #rrggbb, #rrggbbaa, rgb(), rgba(), names."""
    if isinstance(value, bool):
        raise StyleError("bad color %r" % (value,))
    if isinstance(value, int):
        if 0 <= value <= 0xFFFFFFFF:
            return value
        raise StyleError("color int out of range: %r" % (value,))
    if isinstance(value, (tuple, list)) and len(value) in (3, 4):
        r, g, b = (_chan(c) for c in value[:3])
        a = _alpha(value[3]) if len(value) == 4 else 255
        return (a << 24) | (r << 16) | (g << 8) | b
    if not isinstance(value, str):
        raise StyleError("bad color %r" % (value,))
    hit = _COLORS.get(value)
    if hit is not None:
        return hit
    out = _parse_color_str(value)
    if len(_COLORS) > 4096:
        _COLORS.clear()
    _COLORS[value] = out
    return out


def _parse_color_str(value: str) -> int:
    s = value.strip().lower()
    if s in NAMED_COLORS:
        return NAMED_COLORS[s]
    if s.startswith("#"):
        h = s[1:]
        if not re.fullmatch(r"[0-9a-f]+", h):
            raise StyleError("bad color %r" % value)
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        if len(h) == 6:
            return 0xFF000000 | int(h, 16)
        if len(h) == 8:  # CSS order #rrggbbaa
            v = int(h, 16)
            return ((v & 0xFF) << 24) | (v >> 8)
        raise StyleError("bad color %r" % value)
    m = _RGB.match(s)
    if m:
        parts = [p.strip() for p in re.split(r"[,\s/]+", m.group(2).strip()) if p.strip()]
        if len(parts) not in (3, 4):
            raise StyleError("bad color %r" % value)
        r, g, b = (_chan(p) for p in parts[:3])
        a = _alpha(parts[3]) if len(parts) == 4 else 255
        return (a << 24) | (r << 16) | (g << 8) | b
    raise StyleError("bad color %r" % value)


def _chan(c: Any) -> int:
    if isinstance(c, str) and c.endswith("%"):
        return max(0, min(255, round(float(c[:-1]) * 2.55)))
    return max(0, min(255, int(round(float(c)))))


def _alpha(a: Any) -> int:
    if isinstance(a, str) and a.endswith("%"):
        return max(0, min(255, round(float(a[:-1]) * 2.55)))
    return max(0, min(255, int(round(float(a) * 255))))


def flatten(style: Any) -> Dict[str, Any]:
    """Merge nested lists/tuples of style dicts (later wins). None/False/'' entries are skipped."""
    out: Dict[str, Any] = {}
    _merge(out, style)
    return out


def _merge(out: Dict[str, Any], style: Any) -> None:
    if style is None or style is False or style == "":
        return
    if isinstance(style, dict):
        for k, v in style.items():
            out[k] = v
        return
    if isinstance(style, (list, tuple)):
        for s in style:
            _merge(out, s)
        return
    raise StyleError("style must be dict, list or None, got %r" % (type(style).__name__,))


def expand(style: Dict[str, Any]) -> Dict[str, Any]:
    """Expand shorthands into longhand keys. Specific keys win over broader ones regardless of dict order."""
    out: Dict[str, Any] = {}
    # broad -> narrow so narrower keys override
    for fam in _EDGE_FAMILIES:
        if fam in style:
            for e in _EDGES:
                out["%s_%s" % (fam, e)] = style[fam]
        if fam + "_horizontal" in style:
            out[fam + "_left"] = out[fam + "_right"] = style[fam + "_horizontal"]
        if fam + "_vertical" in style:
            out[fam + "_top"] = out[fam + "_bottom"] = style[fam + "_vertical"]
    if "border_width" in style:
        for e in _EDGES:
            out["border_%s_width" % e] = style["border_width"]
    if "border_color" in style:
        for e in _EDGES:
            out["border_%s_color" % e] = style["border_color"]
    if "border_radius" in style:
        for c in _CORNERS:
            out["border_%s_radius" % c] = style["border_radius"]
    if "gap" in style:
        out["row_gap"] = out["column_gap"] = style["gap"]
    if "flex" in style:
        f = style["flex"]
        if isinstance(f, (int, float)) and not isinstance(f, bool):
            out["flex_grow"] = max(f, 0)
            out["flex_shrink"] = 1 if f > 0 else 0
            out["flex_basis"] = 0 if f > 0 else "auto"
    tf = style.get("transform")
    if isinstance(tf, (list, tuple)):  # RN style: transform=[{"translate_y": 10}, {"scale": 2}]
        for item in tf:
            out.update(item)
    for k, v in style.items():
        if k == "transform" and isinstance(tf, (list, tuple)):
            continue
        if k in ("margin", "padding", "border_width", "border_color", "border_radius", "gap", "flex") \
                or k.endswith(("_horizontal", "_vertical")) and k.rsplit("_", 1)[0] in _EDGE_FAMILIES:
            continue
        out[k] = v
    return out


def normalize(style: Any, *, warn: bool = False) -> Dict[str, Any]:
    """flatten + expand + colors to ARGB ints. Returns a plain dict ready for the wire (protocol v2).
    Results are cached by style content, so re-rendering unchanged styles costs one hash."""
    key = None if warn else _cache_key(style)
    if key is not None:
        hit = _NORMALIZED.get(key)
        if hit is not None:
            return dict(hit)
    out = _normalize(style, warn)
    if key is not None:
        if len(_NORMALIZED) > 2048:
            _NORMALIZED.clear()
        _NORMALIZED[key] = out
        return dict(out)
    return out


def _cache_key(style: Any) -> Any:
    """Hashable content key, or None for styles holding unhashable or animated values."""
    if style is None or style is False or style == "":
        return ()
    try:
        if isinstance(style, dict):
            for v in style.values():
                if getattr(v, "_is_animated", False):
                    return None
            # value type is part of the key: 1, 1.0 and True hash and compare equal but normalize differently
            key = tuple((k, v.__class__, v) for k, v in style.items())
            hash(key)
            return key
        if isinstance(style, (list, tuple)):
            parts = []
            for s in style:
                k = _cache_key(s)
                if k is None:
                    return None
                if k:
                    parts.append(k)
            return ("L", tuple(parts))
    except TypeError:
        return None
    return None


def _normalize(style: Any, warn: bool) -> Dict[str, Any]:
    flat = expand(flatten(style))
    out: Dict[str, Any] = {}
    for k, v in flat.items():
        if v is None:
            continue
        if warn and k not in KNOWN_KEYS and k not in out:
            _warn("unknown style key %r" % k)
        if getattr(v, "_is_animated", False):
            v = v._wire()
        elif k == "color" or k == "background_color" or k.endswith("_color"):
            v = parse_color(v)
        elif k == "linear_gradient":
            v = _gradient(v)
        out[k] = v
    fam = out.get("font_family")
    if isinstance(fam, str):
        from . import fonts
        path = fonts.resolve(fam)
        if path:
            out["font_file"] = path
    return out


def _gradient(g: Any) -> Dict[str, Any]:
    """{"angle": deg (0 = to top, 90 = to right, 180 = to bottom, default), "colors": [...], "stops": [0..1]}."""
    if not isinstance(g, dict) or not isinstance(g.get("colors"), (list, tuple)) or len(g["colors"]) < 2:
        raise StyleError("linear_gradient needs a dict with at least 2 colors")
    colors = [parse_color(c) for c in g["colors"]]
    stops = g.get("stops")
    if stops is None:
        n = len(colors)
        stops = [i / (n - 1) for i in range(n)]
    elif len(stops) != len(colors):
        raise StyleError("linear_gradient stops must match colors")
    return {"angle": float(g.get("angle", 180)), "colors": colors, "stops": [float(x) for x in stops]}


_warned: set = set()


def _warn(msg: str) -> None:
    if msg not in _warned:
        _warned.add(msg)
        sys.stderr.write("[pyxpo] style warning: %s\n" % msg)


class StyleSheet:
    """Like React Native's StyleSheet: validates once, returns plain dicts."""

    @staticmethod
    def create(styles: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for name, s in styles.items():
            normalize(s, warn=True)  # validate (raises StyleError on bad values)
            out[name] = dict(s)
        return out

    @staticmethod
    def flatten(style: Any) -> Dict[str, Any]:
        return flatten(style)

    @staticmethod
    def compose(a: Any, b: Any) -> List[Any]:
        return [a, b]

    absolute_fill: Dict[str, Any] = {"position": "absolute", "top": 0, "right": 0, "bottom": 0, "left": 0}
    hairline_width = 1.0 / 3  # refined natively via PixelRatio
