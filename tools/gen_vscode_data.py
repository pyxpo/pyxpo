"""Write the VS Code extension's data file from pyxpo itself, so completions follow the framework.

    python tools/gen_vscode_data.py          # writes editors/vscode/data/pyxpo.json
    python tools/gen_vscode_data.py --check  # exit 1 when the file is stale

Style keys come from `pyxpo.style.KNOWN_KEYS`, components from `pyxpo.__init__` (function components from their
signatures, host components from the "RN props:" list in their docstrings), `[tool.pyxpo]` from the config schema.
"""
from __future__ import annotations

import argparse
import inspect
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pyxpo  # noqa: E402
from pyxpo import app_config, style  # noqa: E402
from pyxpo._keys import to_snake  # noqa: E402

OUT = ROOT / "editors" / "vscode" / "data" / "pyxpo.json"

# Values native accepts. Layout words match with '-' or '_' and any case; RN's spelling is offered.
ALIGN = ["flex-start", "center", "flex-end", "stretch", "baseline"]
JUSTIFY = ["flex-start", "center", "flex-end", "space-between", "space-around", "space-evenly"]
ENUMS: Dict[str, List[str]] = {
    "display": ["flex", "none"],
    "position": ["relative", "absolute"],
    "overflow": ["visible", "hidden", "scroll"],
    "flex_direction": ["column", "row", "column-reverse", "row-reverse"],
    "flex_wrap": ["nowrap", "wrap", "wrap-reverse"],
    "justify_content": JUSTIFY,
    "align_items": ALIGN,
    "align_self": ["auto"] + ALIGN,
    "align_content": ["flex-start", "center", "flex-end", "stretch", "space-between", "space-around",
                      "space-evenly"],
    "font_weight": ["normal", "bold", "100", "200", "300", "400", "500", "600", "700", "800", "900"],
    "font_style": ["normal", "italic"],
    "text_align": ["auto", "left", "center", "right"],
    "text_decoration": ["none", "underline", "line-through", "underline line-through"],
    "text_transform": ["none", "uppercase", "lowercase", "capitalize"],
}

DOCS: Dict[str, str] = {
    "display": "`none` hides the view and takes it out of layout.",
    "position": "`absolute` places the view by `top`/`right`/`bottom`/`left` inside its parent.",
    "z_index": "Stacking order among siblings.",
    "overflow": "`hidden` clips children to the view's bounds.",
    "flex": "Share of the free space along the main axis (RN meaning: positive grows and shrinks).",
    "flex_direction": "Main axis: `column` (default) or `row`.",
    "flex_wrap": "Wrap children onto more lines.",
    "flex_basis": "Size along the main axis before growing or shrinking.",
    "justify_content": "Children along the main axis.",
    "align_items": "Children across the main axis.",
    "align_self": "This view across its parent's main axis (overrides the parent's `align_items`).",
    "align_content": "Lines across the main axis when `flex_wrap` makes more than one.",
    "gap": "Space between children (rows and columns).",
    "aspect_ratio": "Width / height.",
    "linear_gradient": 'Background gradient: `{"colors": [...], "angle": 180, "stops": [0, 1]}`. Angle 0 points '
                       "up, 90 right, 180 down (default). `stops` are optional, 0..1, one per color.",
    "opacity": "0 (invisible) to 1.",
    "elevation": "Android shadow depth.",
    "transform": 'List of single-key dicts, as in RN: `[{"rotate": "45deg"}, {"scale": 1.2}]`.',
    "rotate": 'Rotation: `"45deg"` or radians.',
    "font_weight": "`normal`, `bold` or 100..900.",
    "font_family": "A system family or a font loaded with `use_fonts` / `[tool.pyxpo]` fonts.",
    "line_height": "Line height in dp/pt.",
    "number_of_lines": "Text: cut after this many lines (0 = no limit).",
    "allow_font_scaling": "Text follows the system font size (default True).",
    "text_decoration": "`underline`, `line-through` or both.",
}

GROUPS = [
    (re.compile(r"^margin"), "Outer space"),
    (re.compile(r"^padding"), "Inner space"),
    (re.compile(r"^border_.*radius$"), "Corner radius"),
    (re.compile(r"^border_.*width$"), "Border width"),
    (re.compile(r"^border_.*color$"), "Border color"),
    (re.compile(r"^(top|right|bottom|left|start|end)$"), "Offset from the parent edge"),
    (re.compile(r"^(min_|max_)?(width|height)$"), "Size"),
    (re.compile(r"^shadow_"), "iOS shadow"),
    (re.compile(r"^text_shadow_"), "Text shadow"),
    (re.compile(r"^(scale|scale_x|scale_y|translate_x|translate_y)$"), "Transform shortcut"),
    (re.compile(r"^(flex_grow|flex_shrink)$"), "Flex factor"),
    (re.compile(r"^(row_gap|column_gap)$"), "Space between children"),
]


def style_kind(key: str) -> str:
    if key in ENUMS:
        return "enum"
    if key == "color" or key.endswith("_color"):
        return "color"
    if key == "linear_gradient":
        return "gradient"
    if key == "transform":
        return "transform"
    if key == "allow_font_scaling":
        return "bool"
    if key in ("font_family", "rotate"):
        return "string"
    return "number"


def style_doc(key: str) -> str:
    if key in DOCS:
        return DOCS[key]
    for rx, text in GROUPS:
        if rx.search(key):
            return "%s (`%s`)." % (text, key)
    if style_kind(key) == "color":
        return "Color: #rgb, #rrggbb, #rrggbbaa, rgb(), rgba() or a name."
    return "Style key `%s`." % key


def style_keys() -> Dict[str, Any]:
    out = {}
    for k in sorted(style.KNOWN_KEYS):
        d: Dict[str, Any] = {"kind": style_kind(k), "doc": style_doc(k)}
        if k in ENUMS:
            d["values"] = ENUMS[k]
        out[k] = d
    return out


SKIP_PARAMS = {"key", "children", "props", "kwargs", "args", "ref"}
# Props a component reads without naming them in its signature or docstring.
EXTRA_PROPS = {"Text": ["number_of_lines", "allow_font_scaling"], "Image": ["source"]}


def _doc(obj: Any) -> str:
    doc = inspect.getdoc(obj) or ""
    return "" if doc.startswith("A function component.") else doc


def _doc_props(doc: str) -> List[str]:
    m = re.search(r"(?:RN props|Props):\s*(.*?)(?:\.\s*$|\.\s+[A-Z`]|\Z)", doc, re.S)
    if not m:
        return []
    names = []
    body = re.sub(r"\([^()]*\)", "", m.group(1))  # "delayLongPress (ms, default 500)": drop the note
    for part in re.split(r"[,\n]", body):
        w = re.match(r"\s*`?([A-Za-z][A-Za-z0-9_]*)", part)
        if w and not part.strip().startswith("plus") and w.group(1) not in ("accessibility",):
            names.append(to_snake(w.group(1)))
    return names


def components() -> Dict[str, Any]:
    from pyxpo.component import Component

    out: Dict[str, Any] = {}
    for name in sorted(dir(pyxpo)):
        obj = getattr(pyxpo, name)
        if not name[:1].isupper() or not callable(obj) or inspect.isclass(obj):
            continue
        fn = obj.fn if isinstance(obj, Component) else obj
        module = getattr(fn, "__module__", "") or ""
        if module == "pyxpo.element":  # host factory: props are listed in the docstring
            doc = _doc(obj)
            props = _doc_props(doc)
        elif module.startswith("pyxpo.components.") and inspect.isfunction(fn):
            sig = inspect.signature(fn)
            props = [p for p in sig.parameters if p not in SKIP_PARAMS
                     and sig.parameters[p].kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)]
            doc = _doc(fn) or _doc(obj)
            props += [p for p in _doc_props(doc) if p not in props]
        else:
            continue
        for extra in EXTRA_PROPS.get(name, []) + ["style", "test_id"]:
            if extra not in props:
                props.append(extra)
        out[name] = {"doc": doc, "props": sorted(set(props), key=props.index)}
    return out


def exports(comps: Dict[str, Any]) -> Dict[str, Any]:
    """`pyxpo.__all__` with a kind and the first paragraph of the doc, for auto-import."""
    from pyxpo.component import Component

    out: Dict[str, Any] = {}
    for name in pyxpo.__all__:
        obj = getattr(pyxpo, name)
        if name in comps:
            kind = "component"
        elif inspect.isclass(obj):
            kind = "class"
        elif name.startswith("use"):
            kind = "hook"
        else:
            kind = "function"
        doc = _doc(obj.fn if isinstance(obj, Component) else obj) or _doc(obj)
        if not doc and hasattr(pyxpo, to_snake(name)):  # camelCase alias of a documented hook
            doc = _doc(getattr(pyxpo, to_snake(name)))
        out[name] = {"kind": kind, "doc": doc.split("\n\n")[0].strip()}
    return out


def build() -> Dict[str, Any]:
    named = {k: "#%06x" % (v & 0xFFFFFF) if (v >> 24) == 0xFF else "#%08x" % (((v & 0xFFFFFF) << 8) | (v >> 24))
             for k, v in style.NAMED_COLORS.items()}
    comps = components()
    return {
        "pyxpo": pyxpo.__version__,
        "style": {"keys": style_keys(), "unsupported": sorted(style.RN_UNSUPPORTED)},
        "named_colors": named,
        "components": comps,
        "exports": exports(comps),
        "config": app_config.json_schema(),
    }


def render() -> str:
    return json.dumps(build(), indent=1, sort_keys=True) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    text = render()
    if a.check:
        if not OUT.exists() or OUT.read_text() != text:
            print("stale: run python tools/gen_vscode_data.py", file=sys.stderr)
            return 1
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text)
    print("wrote", OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
