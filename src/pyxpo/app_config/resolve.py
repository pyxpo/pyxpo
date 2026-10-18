"""Turns a validated `[tool.pyxpo]` table into one fully-defaulted, per-platform view."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from . import images
from .schema import ConfigError

PERM_PREFIX = "android.permission."
# Set by load_config after validation: {module: data} from module build hooks, shipped in `_app_config.json`.
MODULE_DATA = "_module_data"


def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", name) or "PyxpoApp"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "app"


def perm(p: str) -> str:
    return p if "." in p else PERM_PREFIX + p


def _splash(top: Dict[str, Any], plat: Dict[str, Any], bg: str) -> Dict[str, Any]:
    s = dict(top.get("splash") or {})
    s.update(plat.get("splash") or {})
    dark = s.get("dark") or {}
    return {"image": s.get("image"), "image_width": s.get("image_width", 200), "resize_mode": s.get("resize_mode", "contain"),
            "background_color": s.get("background_color") or bg, "dark_image": dark.get("image"),
            "dark_background_color": dark.get("background_color")}


def _icon(v: Any) -> Dict[str, Any]:
    if not v:
        return {}
    return {"light": v} if isinstance(v, str) else {k: x for k, x in v.items() if x}


def resolve(cfg: Dict[str, Any], project: Path, project_version: str = "") -> Dict[str, Any]:
    ios, android = cfg.get("ios") or {}, cfg.get("android") or {}
    name = str(cfg.get("name") or Path(project).name)
    bundle = str(cfg.get("bundle_id", "com.example.app"))
    schemes = cfg.get("scheme") or bundle
    schemes = [schemes] if isinstance(schemes, str) else list(schemes)
    build = cfg.get("build_number", 1)
    bg = cfg.get("background_color") or "#FFFFFF"
    style = cfg.get("user_interface_style", "automatic")
    sb, nb = cfg.get("status_bar") or {}, cfg.get("navigation_bar") or {}
    bp = (cfg.get("build_properties") or {}).get("android") or {}
    pk = bp.get("packaging_options") or {}
    if bp.get("enable_shrink_resources_in_release_builds") and not bp.get("enable_minify_in_release_builds"):
        raise ConfigError("build_properties.android: enable_shrink_resources_in_release_builds needs "
                          "enable_minify_in_release_builds = true (Android removes unused resources only with code shrinking)")
    ic = cfg.get("icon")
    ai = android.get("adaptive_icon") or {}
    return {
        "name": name, "product_name": safe_name(name), "slug": cfg.get("slug") or slugify(name),
        "version": str(cfg.get("version") or project_version or "1.0.0"), "build_number": int(build),
        "bundle_id": bundle, "scheme": schemes[0], "schemes": schemes,
        "orientation": cfg.get("orientation", "default"), "user_interface_style": style, "background_color": bg,
        "status_bar": {"style": sb.get("style", "auto"), "hidden": bool(sb.get("hidden", False))},
        "navigation_bar": {"style": nb.get("style", "auto"), "hidden": bool(nb.get("hidden", False))},
        "extra": dict(cfg.get("extra") or {}), "plugins": list(cfg.get("plugins") or []),
        "module_data": dict(cfg.get(MODULE_DATA) or {}),
        "ios": {
            "bundle_id": ios.get("bundle_identifier", bundle), "build_number": str(ios.get("build_number", build)),
            "team_id": str(ios.get("team_id", "")), "supports_tablet": bool(ios.get("supports_tablet", True)),
            "require_full_screen": bool(ios.get("require_full_screen", False)),
            "deployment_target": str(ios.get("deployment_target", "15.0")),
            "icon": _icon(ios.get("icon") or ic), "associated_domains": list(ios.get("associated_domains") or []),
            "uses_apple_sign_in": bool(ios.get("uses_apple_sign_in", False)),
            "background_color": ios.get("background_color") or bg,
            "user_interface_style": ios.get("user_interface_style", style),
            "orientation": ios.get("orientation", cfg.get("orientation", "default")),
            "uses_non_exempt_encryption": (ios.get("config") or {}).get("uses_non_exempt_encryption"),
            "info_plist": dict(ios.get("info_plist") or {}), "entitlements": dict(ios.get("entitlements") or {}),
            "splash": _splash(cfg, ios, ios.get("background_color") or bg),
        },
        "android": {
            "package": android.get("package", bundle), "version_code": int(android.get("version_code", build)),
            "keystore": str(android.get("keystore", "")), "key_alias": str(android.get("key_alias", "")),
            "min_sdk": int(android.get("min_sdk", 24)), "target_sdk": int(android.get("target_sdk", 35)),
            "compile_sdk": int(android.get("compile_sdk", 35)),
            "permissions": [perm(p) for p in android.get("permissions") or []],
            "blocked_permissions": [perm(p) for p in android.get("blocked_permissions") or []],
            "icon": android.get("icon") or ic,
            "adaptive_icon": {k: v for k, v in ai.items() if v},
            "intent_filters": list(android.get("intent_filters") or []),
            "software_keyboard_layout_mode": android.get("software_keyboard_layout_mode", "resize"),
            "allow_backup": bool(android.get("allow_backup", False)),
            "uses_cleartext_traffic": android.get("uses_cleartext_traffic"),
            "predictive_back_gesture_enabled": bool(android.get("predictive_back_gesture_enabled", False)),
            "background_color": android.get("background_color") or bg,
            "user_interface_style": android.get("user_interface_style", style),
            "orientation": android.get("orientation", cfg.get("orientation", "default")),
            "splash": _splash(cfg, android, android.get("background_color") or bg),
            "build_properties": {
                "minify": bool(bp.get("enable_minify_in_release_builds", False)),
                "shrink": bool(bp.get("enable_shrink_resources_in_release_builds", False)),
                "proguard_rules": str(bp.get("extra_proguard_rules", "")),
                "pick_first": list(pk.get("pick_first") or []), "exclude": list(pk.get("exclude") or []),
            },
        },
    }


def check_assets(r: Dict[str, Any], project: Path, cfg: Dict[str, Any]) -> List[str]:
    """Cross-checks that need the filesystem. Returns warnings; raises ConfigError for missing or bad images."""
    warns: List[str] = []
    project = Path(project)

    def need(rel: str, where: str) -> Tuple[Path, Dict[str, Any]]:
        p = project / rel
        if not p.is_file():
            raise ConfigError("%s: file not found: %s" % (where, p))
        try:
            return p, images.info(p)
        except ValueError as e:
            raise ConfigError("%s: %s" % (where, e))

    for k, rel in r["ios"]["icon"].items():
        p, i = need(rel, "ios.icon.%s" % k)
        if i["width"] != i["height"] or i["width"] < 1024:
            raise ConfigError("ios.icon.%s: must be square and at least 1024x1024, got %dx%d" % (k, i["width"], i["height"]))
        if i["has_alpha"] and k == "light":
            warns.append("ios.icon.light has transparency; the App Store rejects icons with an alpha channel")
    a = r["android"]
    if a["icon"]:
        need(a["icon"], "android.icon")
    for k in ("foreground_image", "background_image", "monochrome_image"):
        if a["adaptive_icon"].get(k):
            need(a["adaptive_icon"][k], "android.adaptive_icon.%s" % k)
    for plat, d in (("ios", r["ios"]), ("android", a)):
        for key in ("image", "dark_image"):
            if d["splash"].get(key):
                need(d["splash"][key], "%s.splash.%s" % (plat, key))
    ex = r["extra"]
    for k in ex:
        if re.search(r"secret|password|token|private", k, re.I):
            warns.append("extra.%s looks like a secret; everything in extra ships in plain text inside the app" % k)
    return warns
