"""Themed UI kit built from View/Text/Pressable. Every component reads `use_theme()` and accepts `style`
(and where relevant `text_style`) to override anything."""
from __future__ import annotations

from typing import Any, Callable, Optional

from .component import component
from .element import Text, TextInput, View
from .theme import use_theme
from .ui import Pressable, SafeArea


@component
def Typography(*children: Any, variant: str = "body", color: Optional[str] = None, muted: bool = False,
               style: Any = None, **props: Any):
    """Themed Text. `variant`: display, title, heading, subheading, body, label, caption."""
    t = use_theme()
    base = {"color": color or t["colors"]["text_muted" if muted else "text"], **t["text"].get(variant, t["text"]["body"])}
    return Text(*children, style=[base, style], **props)


@component
def Screen(*children: Any, scroll: bool = False, padding: Optional[float] = None, style: Any = None, **props: Any):
    """Full-screen themed background inside the safe area."""
    t = use_theme()
    pad = t["spacing"]["lg"] if padding is None else padding
    body = [{"flex": 1, "background_color": t["colors"]["background"], "padding": pad}, style]
    if scroll:
        from .element import ScrollView
        return SafeArea(ScrollView(*children, content_container_style=[{"padding": pad}, style],
                                   style={"flex": 1}, **props),
                        style={"flex": 1, "background_color": t["colors"]["background"]})
    return SafeArea(View(*children, style=body, **props), style={"flex": 1, "background_color": t["colors"]["background"]})


@component
def Card(*children: Any, on_press: Optional[Callable[[], Any]] = None, elevated: bool = True, style: Any = None,
         **props: Any):
    t = use_theme()
    c = t["colors"]
    st = [{"background_color": c["surface"], "border_radius": t["radius"]["lg"], "padding": t["spacing"]["lg"],
           "border_width": 1, "border_color": c["border"]},
          {"shadow_color": "#000000", "shadow_opacity": 0.08, "shadow_radius": 8, "shadow_offset_y": 2,
           "elevation": 2} if elevated and not t["dark"] else None, style]
    if on_press is not None:
        return Pressable(*children, on_press=on_press, style=st, **props)
    return View(*children, style=st, **props)


@component
def Divider(vertical: bool = False, inset: float = 0, style: Any = None):
    c = use_theme()["colors"]["border"]
    base = {"width": 1, "align_self": "stretch", "margin_vertical": inset} if vertical else \
        {"height": 1, "align_self": "stretch", "margin_horizontal": inset}
    return View(style=[{"background_color": c}, base, style])


@component
def AppButton(label: str = "", on_press: Optional[Callable[[], Any]] = None, variant: str = "solid",
              tone: str = "primary", size: str = "md", disabled: bool = False, loading: bool = False,
              left: Any = None, full_width: bool = False, style: Any = None, text_style: Any = None, **props: Any):
    """Themed button. `variant`: solid, outline, soft, ghost. `tone`: primary, secondary, success, warning, danger.
    `size`: sm, md, lg."""
    t = use_theme()
    c = t["colors"]
    main = c.get(tone, c["primary"])
    on = c.get("on_" + tone, "#ffffff")
    h, fs, px = {"sm": (32, 13, 12), "md": (44, 15, 16), "lg": (52, 17, 24)}.get(size, (44, 15, 16))
    if variant == "solid":
        bg, fg, border = main, on, main
    elif variant == "soft":  # tinted background, tone-coloured text
        bg, fg, border = (main + "22" if main.startswith("#") and len(main) == 7 else c["surface_alt"]), main, "transparent"
    elif variant == "outline":
        bg, fg, border = "transparent", main, main
    else:
        bg, fg, border = "transparent", main, "transparent"
    box = {"height": h, "padding_horizontal": px, "border_radius": t["radius"]["md"], "background_color": bg,
           "border_width": 1, "border_color": border, "flex_direction": "row", "align_items": "center",
           "justify_content": "center", "align_self": "stretch" if full_width else "flex-start"}
    return Pressable(left, Text("…" if loading else label, style=[{"number_of_lines": 1, "color": fg, "font_size": fs, "font_weight": "600",
                                                                 "margin_left": 6 if left is not None else 0}, text_style]),
                     on_press=None if loading else on_press, disabled=disabled, accessibility_role="button",
                     accessibility_label=label, style=[box, style], **props)


@component
def Badge(label: Any = "", tone: str = "primary", style: Any = None):
    t = use_theme()
    c = t["colors"]
    return View(Text(str(label), style={"color": c.get("on_" + tone, "#ffffff"), "font_size": 11, "font_weight": "600"}),
                style=[{"background_color": c.get(tone, c["primary"]), "border_radius": t["radius"]["pill"],
                        "padding_horizontal": 8, "padding_vertical": 2, "align_self": "flex-start"}, style])


@component
def Avatar(name: str = "", size: float = 40, source: Any = None, style: Any = None):
    """Round avatar: image when `source` is given, else the initials of `name`."""
    from .element import Image
    t = use_theme()
    c = t["colors"]
    box = {"width": size, "height": size, "border_radius": size / 2, "background_color": c["primary"],
           "align_items": "center", "justify_content": "center", "overflow": "hidden"}
    if source is not None:
        return View(Image(source=source, style={"width": size, "height": size}), style=[box, style])
    initials = "".join(w[0] for w in name.split()[:2]).upper()
    return View(Text(initials, style={"color": c["on_primary"], "font_size": size * 0.4, "font_weight": "600"}),
                style=[box, style])


@component
def ListItem(title: str = "", subtitle: Optional[str] = None, left: Any = None, right: Any = None,
             on_press: Optional[Callable[[], Any]] = None, style: Any = None):
    t = use_theme()
    c = t["colors"]
    sp = t["spacing"]
    row = View(
        left, View(Text(title, style={"font_size": 16, "color": c["text"]}),
                   Text(subtitle, style={"font_size": 13, "color": c["text_muted"], "margin_top": 2}) if subtitle else None,
                   style={"flex": 1, "margin_horizontal": sp["md"] if left is not None else 0}),
        right,
        style=[{"flex_direction": "row", "align_items": "center", "padding_vertical": sp["md"],
                "padding_horizontal": sp["lg"], "background_color": c["surface"]}, style])
    if on_press is None:
        return row
    return Pressable(row, on_press=on_press, pressed_opacity=0.7)


@component
def Field(label: Optional[str] = None, error: Optional[str] = None, hint: Optional[str] = None,
          style: Any = None, input_style: Any = None, **props: Any):
    """Labelled TextInput with error/hint line. Extra props go to TextInput (`value`, `on_change_text`, ...)."""
    t = use_theme()
    c = t["colors"]
    border = c["danger"] if error else c["border"]
    props.setdefault("placeholder_color", c["text_muted"])
    return View(
        Text(label, style={"font_size": 13, "font_weight": "600", "color": c["text"], "margin_bottom": 4}) if label else None,
        TextInput(style=[{"height": 44, "padding_horizontal": 12, "border_width": 1, "border_color": border,
                          "border_radius": t["radius"]["md"], "background_color": c["surface"], "color": c["text"],
                          "font_size": 15}, input_style], **props),
        Text(error or hint, style={"font_size": 12, "margin_top": 4, "color": c["danger"] if error else c["text_muted"]})
        if (error or hint) else None,
        style=style)


@component
def ProgressBar(value: float = 0.0, tone: str = "primary", height: float = 6, style: Any = None):
    """`value` in 0..1."""
    t = use_theme()
    c = t["colors"]
    pct = max(0.0, min(1.0, float(value))) * 100
    return View(View(style={"width": "%g%%" % pct, "height": height, "background_color": c.get(tone, c["primary"]),
                            "border_radius": height / 2}),
                style=[{"height": height, "background_color": c["surface_alt"], "border_radius": height / 2,
                        "overflow": "hidden"}, style])
