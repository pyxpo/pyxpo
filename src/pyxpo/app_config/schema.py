"""Declarative `[tool.pyxpo]` schema: validation with exact key paths, "did you mean" hints, JSON Schema export."""
from __future__ import annotations

import difflib
import re
from typing import Any, Dict, List

COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
VERSION = re.compile(r"^\d+(\.\d+){0,2}$")
PACKAGE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*$")


class ConfigError(ValueError):
    """Invalid `[tool.pyxpo]`; the message names the offending key."""


def T(kind: str, doc: str = "", **kw: Any) -> Dict[str, Any]:
    return dict(kind=kind, doc=doc, **kw)


def table(fields: Dict[str, Any], doc: str = "", free: bool = False) -> Dict[str, Any]:
    return dict(kind="table", fields=fields, doc=doc, free=free)


STR_LIST = T("list", item=T("str"))
ORIENT = T("enum", "Screen orientation lock.", values=["default", "portrait", "landscape"])
STYLE = T("enum", "Light/dark appearance.", values=["automatic", "light", "dark"])
BAR = T("enum", "Icon style.", values=["auto", "light", "dark"])
PNG = T("path", "PNG image path, relative to the project.")
HEX = T("color", "#RGB, #RRGGBB or #RRGGBBAA (CSS order).")

SCHEMA = table({
    "name": T("str", "Display name."),
    "slug": T("str", "URL-safe app id; default derived from name."),
    "version": T("version", "User-visible version (MARKETING_VERSION / versionName)."),
    "build_number": T("int", "Build number (CFBundleVersion / versionCode).", min=1),
    "bundle_id": T("package", "Reverse-DNS app id."),
    "scheme": T("scheme", "Deep-link scheme(s)."),
    "orientation": ORIENT,
    "user_interface_style": STYLE,
    "background_color": HEX,
    "icon": PNG,
    "modules": STR_LIST, "targets": STR_LIST, "requires": STR_LIST, "abis": STR_LIST, "wheel_index": STR_LIST,
    "plugins": T("list", "Config plugins: './file.py', 'pkg.mod[:fn]' or ['entry', {options}].", item=T("any")),
    "allow_4kb_libs": T("bool"), "dev_port": T("int", min=1, max=65535),
    "splash": table({
        "image": PNG,
        "image_width": T("int", "Logical width in points/dp.", min=1),
        "resize_mode": T("enum", values=["contain", "cover", "native"]),
        "background_color": HEX,
        "dark": table({"image": PNG, "background_color": HEX}),
    }),
    "status_bar": table({"style": BAR, "hidden": T("bool")}),
    "navigation_bar": table({"style": BAR, "hidden": T("bool")}, "Android only."),
    "ios": table({
        "bundle_identifier": T("package"), "build_number": T("build"), "team_id": T("str"),
        "supports_tablet": T("bool"), "require_full_screen": T("bool"),
        "deployment_target": T("version", min_version="15.0"),
        "icon": T("icon", "PNG path, or {light, dark, tinted} table."),
        "associated_domains": STR_LIST, "uses_apple_sign_in": T("bool"),
        "background_color": HEX, "user_interface_style": STYLE, "orientation": ORIENT,
        "config": table({"uses_non_exempt_encryption": T("bool")}),
        "info_plist": T("dict", "Raw Info.plist keys (merged last)."),
        "infoPlist": T("dict", "Module Info.plist defaults (native-module convention)."),
        "entitlements": T("dict", "Raw entitlements."),
        "splash": table({"image": PNG, "background_color": HEX, "dark": table({"image": PNG, "background_color": HEX})}),
    }),
    "android": table({
        "package": T("package"), "version_code": T("int", min=1), "keystore": T("str"), "key_alias": T("str"),
        "min_sdk": T("int", min=24), "target_sdk": T("int", min=24), "compile_sdk": T("int", min=24),
        "permissions": STR_LIST, "blocked_permissions": STR_LIST,
        "adaptive_icon": table({"foreground_image": PNG, "background_image": PNG, "background_color": HEX,
                                "monochrome_image": PNG}),
        "icon": PNG,
        "intent_filters": T("list", item=T("dict")),
        "software_keyboard_layout_mode": T("enum", values=["resize", "pan"]),
        "allow_backup": T("bool"), "uses_cleartext_traffic": T("bool"), "predictive_back_gesture_enabled": T("bool"),
        "background_color": HEX, "user_interface_style": STYLE, "orientation": ORIENT,
        "splash": table({"image": PNG, "background_color": HEX, "dark": table({"image": PNG, "background_color": HEX})}),
    }),
    "windows": table({
        "title": T("str", "Window title; default the app name."),
        "size": T("list", "Window size [width, height] in pixels at 100% scale; default [1024, 768].",
                  item=T("int", min=1)),
    }, "Native Windows desktop app."),
    "build_properties": table({
        "android": table({
            "enable_minify_in_release_builds": T("bool"),
            "enable_shrink_resources_in_release_builds": T("bool"),
            "extra_proguard_rules": T("str"),
            "packaging_options": table({"pick_first": STR_LIST, "exclude": STR_LIST}),
        }),
    }),
    "module_options": T("dict", "Per-module options, keyed by module name."),
    "extra": T("dict", "Free-form values shipped inside the app (never put secrets here)."),
}, "pyxpo app configuration")


def camel_to_snake(k: str) -> str:
    return re.sub(r"(?<=[a-z0-9])([A-Z])", lambda m: "_" + m.group(1).lower(), k).lower()


def normalize(cfg: Dict[str, Any], spec: Dict[str, Any] = SCHEMA, path: str = "[tool.pyxpo]") -> Dict[str, Any]:
    """Accepts Expo camelCase names for known fields; giving both forms of one field is an error."""
    if spec.get("kind") != "table" or spec.get("free"):
        return cfg
    out: Dict[str, Any] = {}
    fields = spec["fields"]
    for k, v in cfg.items():
        key = k
        if k not in fields:
            snake = camel_to_snake(k)
            if snake in fields:
                if snake in cfg:
                    raise ConfigError("%s: both %r and %r are set; keep one" % (path, k, snake))
                key = snake
        sub = fields.get(key)
        out[key] = normalize(v, sub, "%s.%s" % (path.rstrip("]"), key) if path.endswith("]") else path + "." + key) \
            if isinstance(v, dict) and sub and sub.get("kind") == "table" else v
    return out


def _png_ok(v: Any) -> bool:
    return isinstance(v, str) and v.lower().endswith(".png")


def _check(v: Any, s: Dict[str, Any], where: str, errs: List[str]) -> None:
    kind = s["kind"]

    def bad(msg: str) -> None:
        errs.append("%s: %s, got %r" % (where, msg, v))

    if kind == "table":
        if not isinstance(v, dict):
            return bad("expected a table")
        fields = s["fields"]
        for k, sv in v.items():
            if k in fields:
                _check(sv, fields[k], "%s.%s" % (where, k) if not where.endswith("]") else "%s %s" % (where, k), errs)
            else:
                hint = difflib.get_close_matches(k, fields, n=1)
                errs.append("%s: unknown key %r%s" % (where, k, " (did you mean %r?)" % hint[0] if hint else ""))
    elif kind == "str":
        if not isinstance(v, str):
            bad("expected a string")
    elif kind == "bool":
        if not isinstance(v, bool):
            bad("expected true or false")
    elif kind == "int":
        if isinstance(v, bool) or not isinstance(v, int):
            return bad("expected an integer")
        if "min" in s and v < s["min"]:
            bad("expected an integer >= %d" % s["min"])
        elif "max" in s and v > s["max"]:
            bad("expected an integer <= %d" % s["max"])
    elif kind == "build":
        if not (isinstance(v, (int, str)) and not isinstance(v, bool) and re.match(r"^\d+(\.\d+)*$", str(v))):
            bad("expected a number like 7 or \"7\"")
    elif kind == "enum":
        if v not in s["values"]:
            bad("expected one of %s" % ", ".join(s["values"]))
    elif kind == "color":
        if not (isinstance(v, str) and COLOR.match(v)):
            bad("expected a color like #RRGGBB or #RRGGBBAA")
    elif kind == "version":
        if not (isinstance(v, str) and VERSION.match(v)):
            return bad("expected a version string like \"1.2.0\"")
        mv = s.get("min_version")
        if mv and tuple(int(x) for x in v.split(".")) < tuple(int(x) for x in mv.split(".")):
            bad("expected >= %s" % mv)
    elif kind == "package":
        if not (isinstance(v, str) and PACKAGE.match(v)):
            bad("expected a reverse-DNS id like com.acme.app")
    elif kind == "scheme":
        items = v if isinstance(v, list) else [v]
        if not items or not all(isinstance(i, str) and (SCHEME.match(i) or PACKAGE.match(i)) for i in items):
            bad("expected a URL scheme or a list of them")
    elif kind == "path":
        if not _png_ok(v):
            bad("expected a .png path")
    elif kind == "icon":
        if isinstance(v, dict):
            for k, sv in v.items():
                if k not in ("light", "dark", "tinted"):
                    errs.append("%s: unknown key %r (use light, dark, tinted)" % (where, k))
                elif not _png_ok(sv):
                    errs.append("%s.%s: expected a .png path, got %r" % (where, k, sv))
        elif not _png_ok(v):
            bad("expected a .png path or a {light, dark, tinted} table")
    elif kind == "list":
        if not isinstance(v, list):
            return bad("expected a list")
        for i, item in enumerate(v):
            _check(item, s["item"], "%s[%d]" % (where, i), errs)
    elif kind == "dict":
        if not isinstance(v, dict):
            bad("expected a table")


def validate(cfg: Dict[str, Any]) -> None:
    """Raises ConfigError listing every problem (unknown keys, wrong types, out-of-range values)."""
    errs: List[str] = []
    _check(cfg, SCHEMA, "[tool.pyxpo]", errs)
    if errs:
        raise ConfigError("invalid pyproject.toml:\n  " + "\n  ".join(errs))


def json_schema(spec: Dict[str, Any] = SCHEMA) -> Dict[str, Any]:
    kind = spec["kind"]
    out: Dict[str, Any]
    if kind == "table":
        out = {"type": "object", "properties": {k: json_schema(v) for k, v in spec["fields"].items()},
               "additionalProperties": False}
    elif kind == "list":
        out = {"type": "array", "items": json_schema(spec["item"])}
    elif kind in ("int",):
        out = {"type": "integer"}
        if "min" in spec:
            out["minimum"] = spec["min"]
        if "max" in spec:
            out["maximum"] = spec["max"]
    elif kind == "bool":
        out = {"type": "boolean"}
    elif kind == "enum":
        out = {"enum": spec["values"]}
    elif kind == "color":
        out = {"type": "string", "pattern": COLOR.pattern}
    elif kind == "scheme":
        out = {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]}
    elif kind == "build":
        out = {"type": ["integer", "string"]}
    elif kind in ("dict",):
        out = {"type": "object"}
    elif kind == "icon":
        out = {"oneOf": [{"type": "string"}, {"type": "object"}]}
    elif kind == "any":
        out = {}
    else:
        out = {"type": "string"}
    if spec.get("doc"):
        out["description"] = spec["doc"]
    return out
