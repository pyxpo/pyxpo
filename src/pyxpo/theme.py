"""Theming: a plain-dict `Theme`, light/dark presets, `ThemeProvider` and `use_theme()`.

    ThemeProvider(App_body, mode="system")            # follows the OS light/dark setting
    ThemeProvider(body, theme=create_theme(light_theme, colors={"primary": "#e91e63"}))

A theme is a dict with `colors`, `spacing`, `radius`, `font_sizes`, `text` (typography variants) and
`dark`. `use_theme()` works without a provider and then returns `light_theme`.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, Optional

from .component import component
from .env import use_color_scheme
from .hooks import create_context, use_context

Theme = Dict[str, Any]

_SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32}
_RADIUS = {"sm": 4, "md": 8, "lg": 12, "xl": 20, "pill": 999}
_FONT_SIZES = {"xs": 11, "sm": 13, "md": 15, "lg": 17, "xl": 22, "xxl": 28, "xxxl": 34}
_TEXT = {
    "display": {"font_size": 34, "font_weight": "700"},
    "title": {"font_size": 28, "font_weight": "700"},
    "heading": {"font_size": 22, "font_weight": "600"},
    "subheading": {"font_size": 17, "font_weight": "600"},
    "body": {"font_size": 15},
    "label": {"font_size": 13, "font_weight": "600"},
    "caption": {"font_size": 12},
}

light_theme: Theme = {
    "dark": False,
    "colors": {
        "background": "#f5f5f7", "surface": "#ffffff", "surface_alt": "#ececf0",
        "text": "#111111", "text_muted": "#6b6b76", "border": "#d8d8de", "overlay": "#00000066",
        "primary": "#1a73e8", "on_primary": "#ffffff", "secondary": "#6c5ce7", "on_secondary": "#ffffff",
        "success": "#1e9e5a", "warning": "#e69500", "danger": "#d93025", "on_danger": "#ffffff",
    },
    "spacing": _SPACING, "radius": _RADIUS, "font_sizes": _FONT_SIZES, "text": _TEXT,
}

dark_theme: Theme = {
    "dark": True,
    "colors": {
        "background": "#0e0e10", "surface": "#1c1c20", "surface_alt": "#2a2a30",
        "text": "#f2f2f5", "text_muted": "#9a9aa6", "border": "#38383f", "overlay": "#000000aa",
        "primary": "#4d94ff", "on_primary": "#ffffff", "secondary": "#8c7ff0", "on_secondary": "#ffffff",
        "success": "#3ccf84", "warning": "#ffb020", "danger": "#ff5a4d", "on_danger": "#ffffff",
    },
    "spacing": _SPACING, "radius": _RADIUS, "font_sizes": _FONT_SIZES, "text": _TEXT,
}


def _merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def create_theme(base: Optional[Theme] = None, **overrides: Any) -> Theme:
    """Deep-merge `overrides` (e.g. `colors={...}`, `text={"body": {...}}`) onto `base` (default light)."""
    return _merge(base or light_theme, overrides)


_ThemeContext = create_context(light_theme)


def use_theme() -> Theme:
    return use_context(_ThemeContext)


@component
def ThemeProvider(*children: Any, theme: Optional[Theme] = None, mode: str = "system",
                  light: Optional[Theme] = None, dark: Optional[Theme] = None):
    """Provide a theme to the subtree. `theme` pins one theme; otherwise `mode` is `system`, `light` or `dark`
    and picks `light`/`dark` (defaults: the presets)."""
    scheme = use_color_scheme()
    if theme is not None:
        chosen = theme
    elif mode == "dark" or (mode == "system" and scheme == "dark"):
        chosen = dark or dark_theme
    else:
        chosen = light or light_theme
    return _ThemeContext.Provider(*children, value=chosen)
