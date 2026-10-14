"""Navigation header (react-navigation style) shared by Stack, Drawer and Tabs screens."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from ...component import Component, component
from ...components.pressable import Pressable
from ...components.status_bar import StatusBar
from ...components.text import Text
from ...components.view import View
from ...hooks import create_context, use_context, use_effect, use_safe_area_insets
from ...vector_icons import Feather
from ..theme import useTheme

# False once an ancestor header already paints under the status bar.
TopInset = create_context(True)


def resolve(value: Any, props: Dict[str, Any]) -> Any:
    """`headerLeft`/`headerRight`/`headerTitle` may be an element, or a callable taking `{tintColor, ...}`; a component is rendered bare."""
    if isinstance(value, Component):
        return value()
    return value(props) if callable(value) else value


@component
def Header(title: Any = "", can_back: bool = False, on_back: Optional[Callable[[], Any]] = None,
           options: Optional[Dict[str, Any]] = None):
    o = options or {}
    theme = useTheme()
    colors = theme["colors"]
    use_effect(lambda: StatusBar.set_bar_style("light-content" if theme.get("dark") else "dark-content"), [theme.get("dark")])
    inset = use_safe_area_insets()["top"] if use_context(TopInset) else 0
    tint = o.get("headerTintColor") or colors["primary"]
    bar = {"height": 48 + inset, "padding_top": inset, "flex_direction": "row", "align_items": "center",
           "padding_horizontal": 4, "background_color": colors["card"], "border_bottom_width": 1,
           "border_color": colors["border"]}
    hs = o.get("headerStyle") or {}
    if o.get("headerTransparent"):
        bar.update(position="absolute", left=0, right=0, top=0, background_color="transparent", border_bottom_width=0)
    ctx = {"tintColor": tint, "canGoBack": can_back}
    lft = resolve(o.get("headerLeft"), ctx)
    if lft is None:
        show_back = can_back and o.get("headerBackVisible", True)
        lft = (Pressable(Feather(name="chevron-left", size=26, color=tint), on_press=on_back, accessibility_label="Back",
                         style={"width": 40, "height": 40, "align_items": "center", "justify_content": "center"})
               if show_back else View(style={"width": 8}))
    t = resolve(o.get("headerTitle"), {"children": title, "tintColor": tint})
    if t is None or isinstance(t, str):
        t = Text(str(title if t is None else t), number_of_lines=1,
                 style=[{"flex": 1, "font_size": 17, "font_weight": "600", "color": o.get("headerTintColor") or colors["text"]},
                        o.get("headerTitleStyle")])
    return View(lft, t, resolve(o.get("headerRight"), ctx), style=[bar, hs])
