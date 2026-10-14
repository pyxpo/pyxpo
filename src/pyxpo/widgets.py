"""Form and feedback widgets on top of the themed kit: Icon, InputField, PasswordInput, SearchInput, TextArea,
Dropdown, MultiSelect, NumberInput, DatePicker, TimePicker, RadioGroup, Stepper, Chip, Alert, TabBar.

All read `use_theme()` and take `style` to override. Controlled components: pass `value` and the `on_change`
callback, keep state in the parent (like `TextInput`)."""
from __future__ import annotations

import datetime as _dt
from typing import Any, Callable, Dict, List, Optional, Sequence

from .component import component
from .element import Path, Text, TextInput, View
from .icons import icon_commands
from .hooks import use_state
from .theme import use_theme
from .ui import Modal, Pressable

ICONS: Dict[str, str] = {
    "check": "✓", "close": "✕", "plus": "+", "minus": "−", "chevron-down": "▾", "chevron-up": "▴",
    "chevron-right": "›", "chevron-left": "‹", "search": "⌕", "user": "☺", "mail": "✉", "lock": "⚿",
    "eye": "◉", "eye-off": "◎", "calendar": "▦", "clock": "◷", "home": "⌂", "bell": "♫", "grid": "▤",
    "info": "ⓘ", "error": "⚠", "success": "✔", "star": "★", "menu": "☰", "settings": "⚙",
}


_ICON_SCALE: Dict[str, float] = {"lock": 1.35, "mail": 1.3, "clock": 1.4, "calendar": 1.3, "search": 1.2, "eye": 1.2,
                                  "eye-off": 1.2, "grid": 1.1}


def _s(children: Any) -> str:
    """Text of positional string children (strings reach components as Text elements)."""
    return "".join(str(getattr(x, "props", {}).get("text", x)) for x in children)


@component
def Icon(*children: Any, name: str = "", size: float = 18, color: Optional[str] = None, style: Any = None):
    """Glyph icon. `name` is a key of `ICONS`; any other string is drawn as is (emoji, a letter, ...)."""
    name = name or _s(children)
    c = use_theme()["colors"]
    col = color or c["text_muted"]
    cmds = icon_commands(name)
    if cmds is not None:
        return Path(d=cmds, stroke=col, stroke_width=2 if size >= 16 else 2.4,
                    style=[{"width": size, "height": size}, style])
    return Text(ICONS.get(name, name), style=[{"font_size": size * _ICON_SCALE.get(name, 1.0), "color": col,
                                                "text_align": "center", "min_width": size}, style])


def _field_box(t: Dict[str, Any], height: Optional[float], focused_error: bool = False) -> Dict[str, Any]:
    c = t["colors"]
    return {"flex_direction": "row", "align_items": "center", "padding_horizontal": 12,
            "border_width": 1, "border_color": c["danger"] if focused_error else c["border"],
            "border_radius": t["radius"]["md"], "background_color": c["surface"],
            **({"height": height} if height is not None else {"min_height": 44})}


@component
def Label(*children: Any, text: str = "", style: Any = None):
    text = text or _s(children)
    c = use_theme()["colors"]
    return Text(text, style=[{"font_size": 13, "font_weight": "600", "color": c["text"], "margin_bottom": 6}, style])


@component
def InputField(label: Optional[str] = None, left: Any = None, right: Any = None, error: Optional[str] = None,
               hint: Optional[str] = None, style: Any = None, input_style: Any = None, **props: Any):
    """TextInput in a bordered box with optional `left`/`right` elements (icons, buttons)."""
    t = use_theme()
    c = t["colors"]
    props.setdefault("placeholder_color", c["text_muted"])
    return View(
        Label(label) if label else None,
        View(left, TextInput(style=[{"flex": 1, "height": 44, "color": c["text"], "font_size": 15,
                                     "margin_left": 8 if left is not None else 0,
                                     "margin_right": 8 if right is not None else 0}, input_style], **props),
             right, style=[_field_box(t, 44, bool(error)), style]),
        Text(error or hint, style={"font_size": 12, "margin_top": 4, "color": c["danger"] if error else c["text_muted"]})
        if (error or hint) else None)


@component
def PasswordInput(label: Optional[str] = "Password", style: Any = None, **props: Any):
    shown, set_shown = use_state(False)
    return InputField(label=label, left=Icon("lock"),
                      right=Pressable(Icon("eye" if shown else "eye-off"), on_press=lambda: set_shown(not shown),
                                      accessibility_label="Toggle password visibility"),
                      secure=not shown, style=style, **props)


@component
def SearchInput(value: str = "", on_change_text: Optional[Callable[[str], Any]] = None, label: Optional[str] = None,
                placeholder: str = "Search...", style: Any = None, **props: Any):
    clear = Pressable(Icon("close"), on_press=lambda: on_change_text("") if on_change_text else None,
                      accessibility_label="Clear") if value else None
    return InputField(label=label, left=Icon("search"), right=clear, value=value, on_change_text=on_change_text,
                      placeholder=placeholder, style=style, **props)


@component
def TextArea(label: Optional[str] = None, lines: int = 4, style: Any = None, **props: Any):
    t = use_theme()
    c = t["colors"]
    props.setdefault("placeholder_color", c["text_muted"])
    return View(Label(label) if label else None,
                TextInput(multiline=True, style=[{"height": 22 * lines + 20, "padding": 12, "color": c["text"],
                                                  "font_size": 15, "border_width": 1, "border_color": c["border"],
                                                  "border_radius": t["radius"]["md"],
                                                  "background_color": c["surface"]},
                                                 style], **props))


@component
def Sheet(*children: Any, visible: bool = False, on_close: Optional[Callable[[], Any]] = None, title: str = "",
          style: Any = None):
    """Bottom sheet (a themed slide Modal)."""
    t = use_theme()
    c = t["colors"]
    return Modal(
        Pressable(style={"flex": 1}, on_press=on_close, accessibility_label="Dismiss"),
        View(Text(title, style={"font_size": 17, "font_weight": "600", "color": c["text"], "margin_bottom": 8}) if title else None,
             *children,
             style=[{"background_color": c["surface"], "padding": 16, "border_top_left_radius": t["radius"]["lg"],
                     "border_top_right_radius": t["radius"]["lg"], "max_height": "70%"}, style]),
        visible=visible, animation_type="slide", transparent=False, on_request_close=on_close)


def _opt(o: Any) -> Dict[str, Any]:
    return o if isinstance(o, dict) else {"value": o, "label": str(o)}


@component
def Dropdown(options: Sequence[Any] = (), value: Any = None, on_change: Optional[Callable[[Any], Any]] = None,
             label: Optional[str] = None, placeholder: str = "Select option", style: Any = None):
    """Single choice. `options`: values or `{"value", "label"}` dicts."""
    t = use_theme()
    c = t["colors"]
    open_, set_open = use_state(False)
    opts = [_opt(o) for o in options]
    cur = next((o for o in opts if o["value"] == value), None)

    def pick(v: Any) -> None:
        set_open(False)
        if on_change:
            on_change(v)

    rows = [Pressable(Text(o["label"], style={"flex": 1, "font_size": 16, "color": c["text"]}),
                      Icon("check", color=c["primary"]) if o["value"] == value else None,
                      on_press=(lambda v=o["value"]: pick(v)), key=str(o["value"]),
                      style={"flex_direction": "row", "align_items": "center", "padding_vertical": 14})
            for o in opts]
    return View(
        Label(label) if label else None,
        Pressable(Text(cur["label"] if cur else placeholder,
                       style={"flex": 1, "font_size": 15, "color": c["text"] if cur else c["text_muted"]}),
                  Icon("chevron-down"), on_press=lambda: set_open(True), accessibility_role="button",
                  style=[_field_box(t, 44), style]),
        Sheet(*rows, visible=open_, on_close=lambda: set_open(False), title=label or placeholder))


@component
def Chip(*children: Any, label: str = "", tone: str = "primary", selected: bool = True, on_press: Optional[Callable[[], Any]] = None,
         on_remove: Optional[Callable[[], Any]] = None, style: Any = None):
    """Pill tag. `selected` solid tone, else soft grey. `on_remove` adds a close button."""
    label = label or _s(children)
    t = use_theme()
    c = t["colors"]
    main = c.get(tone, c["primary"])
    solid = tone in ("primary", "secondary") and selected
    bg = main if solid else c["surface_alt"]
    fg = c.get("on_" + tone, "#ffffff") if solid else (main if tone not in ("neutral",) else c["text"])
    box = {"flex_direction": "row", "align_items": "center", "background_color": bg, "border_radius": t["radius"]["pill"],
           "padding_horizontal": 14, "padding_vertical": 6, "align_self": "flex-start"}
    body = [Text(label, style={"font_size": 14, "font_weight": "500", "color": fg}),
            Pressable(Icon("close", size=12, color=fg), on_press=on_remove, accessibility_label="Remove " + label,
                      style={"margin_left": 6}) if on_remove else None]
    if on_press is not None:
        return Pressable(*body, on_press=on_press, style=[box, style])
    return View(*body, style=[box, style])


@component
def MultiSelect(options: Sequence[Any] = (), value: Sequence[Any] = (), on_change: Optional[Callable[[List[Any]], Any]] = None,
                label: Optional[str] = None, placeholder: str = "Select", style: Any = None):
    t = use_theme()
    c = t["colors"]
    open_, set_open = use_state(False)
    opts = [_opt(o) for o in options]
    chosen = list(value)

    def toggle(v: Any) -> None:
        if on_change:
            on_change([x for x in chosen if x != v] if v in chosen else chosen + [v])

    chips = [Chip(label=o["label"], tone="neutral", on_remove=(lambda v=o["value"]: toggle(v)), key=str(o["value"]),
                  style={"margin_right": 6, "padding_horizontal": 10, "padding_vertical": 4}) for o in opts if o["value"] in chosen]
    rows = [Pressable(Text(o["label"], style={"flex": 1, "font_size": 16, "color": c["text"]}),
                      Icon("check", color=c["primary"]) if o["value"] in chosen else None,
                      on_press=(lambda v=o["value"]: toggle(v)), key=str(o["value"]),
                      style={"flex_direction": "row", "align_items": "center", "padding_vertical": 14})
            for o in opts]
    return View(
        Label(label) if label else None,
        Pressable(View(*chips, style={"flex": 1, "flex_direction": "row", "flex_wrap": "wrap"}) if chips else
                  Text(placeholder, style={"flex": 1, "font_size": 15, "color": c["text_muted"]}),
                  Icon("chevron-down"), on_press=lambda: set_open(True), accessibility_role="button",
                  style=[_field_box(t, None), {"padding_vertical": 6}, style]),
        Sheet(*rows, View(Pressable(Text("Done", style={"color": c["on_primary"], "font_weight": "600"}),
                                    on_press=lambda: set_open(False),
                                    style={"height": 44, "border_radius": t["radius"]["md"], "align_items": "center",
                                           "justify_content": "center", "background_color": c["primary"],
                                           "margin_top": 8})),
              visible=open_, on_close=lambda: set_open(False), title=label or placeholder))


@component
def NumberInput(value: float = 0, on_change: Optional[Callable[[float], Any]] = None, minimum: float = -1e9,
                maximum: float = 1e9, step: float = 1, label: Optional[str] = None, style: Any = None):
    t = use_theme()
    c = t["colors"]

    def bump(d: float) -> None:
        if on_change:
            n = max(minimum, min(maximum, value + d))
            on_change(int(n) if float(n).is_integer() and float(step).is_integer() else n)

    def btn(glyph: str, d: float, off: bool):
        return Pressable(Icon(glyph, size=20, color=c["text_muted"] if off else c["text"]), disabled=off,
                         on_press=lambda: bump(d), accessibility_label="Increase" if d > 0 else "Decrease",
                         style={"width": 32, "height": 32, "border_radius": t["radius"]["sm"], "align_items": "center",
                                "justify_content": "center", "background_color": c["surface_alt"]})

    return View(Label(label) if label else None,
                View(btn("minus", -step, value <= minimum),
                     Text(str(value), style={"flex": 1, "text_align": "center", "font_size": 16, "color": c["text"]}),
                     btn("plus", step, value >= maximum),
                     style=[_field_box(t, 46), {"padding_horizontal": 6}, style]))


@component
def _StepperCol(label: str = "", value: int = 0, on_up: Any = None, on_down: Any = None, text: str = ""):
    t = use_theme()
    c = t["colors"]
    return View(Pressable(Icon("chevron-up"), on_press=on_up, accessibility_label="Next " + label),
                Text(text or str(value), style={"font_size": 20, "font_weight": "600", "color": c["text"],
                                                 "padding_vertical": 6}),
                Pressable(Icon("chevron-down"), on_press=on_down, accessibility_label="Previous " + label),
                style={"align_items": "center", "margin_horizontal": 14})


@component
def DatePicker(value: Optional[_dt.date] = None, on_change: Optional[Callable[[_dt.date], Any]] = None,
               label: Optional[str] = None, style: Any = None):
    """Date field; tap to open a sheet with year / month / day spinners."""
    t = use_theme()
    c = t["colors"]
    open_, set_open = use_state(False)
    cur = value or _dt.date.today()
    draft, set_draft = use_state(cur)

    def shift(field: str, d: int) -> None:
        y, m, day = draft.year, draft.month, draft.day
        if field == "y":
            y += d
        elif field == "m":
            m = (m - 1 + d) % 12 + 1
        else:
            day += d
        day = max(1, min(day, _days_in(y, m)))
        set_draft(_dt.date(max(1, y), m, day))

    def done() -> None:
        set_open(False)
        if on_change:
            on_change(draft)

    return View(
        Label(label) if label else None,
        Pressable(Icon("calendar"), Text(cur.strftime("%b %d, %Y"), style={"flex": 1, "margin_left": 8, "font_size": 14, "number_of_lines": 1,
                                                                           "color": c["text"]}),
                  on_press=lambda: (set_draft(cur), set_open(True)), accessibility_role="button",
                  style=[_field_box(t, 46), style]),
        Sheet(View(_StepperCol(label="month", value=draft.month, on_up=lambda: shift("m", 1), on_down=lambda: shift("m", -1), text=draft.strftime("%b")),
                   _StepperCol(label="day", value=draft.day, on_up=lambda: shift("d", 1), on_down=lambda: shift("d", -1)),
                   _StepperCol(label="year", value=draft.year, on_up=lambda: shift("y", 1), on_down=lambda: shift("y", -1)),
                   style={"flex_direction": "row", "justify_content": "center"}),
              _done_button(done), visible=open_, on_close=lambda: set_open(False), title=label or "Select date"))


def _days_in(y: int, m: int) -> int:
    nxt = _dt.date(y + (m == 12), m % 12 + 1, 1)
    return (nxt - _dt.timedelta(days=1)).day


@component
def _DoneButton(on_press: Any = None):
    t = use_theme()
    c = t["colors"]
    return Pressable(Text("Done", style={"color": c["on_primary"], "font_weight": "600", "font_size": 16}),
                     on_press=on_press, accessibility_role="button",
                     style={"height": 46, "border_radius": t["radius"]["md"], "align_items": "center",
                            "justify_content": "center", "background_color": c["primary"], "margin_top": 16})


def _done_button(on_press: Any):
    return _DoneButton(on_press=on_press)


@component
def TimePicker(value: Optional[_dt.time] = None, on_change: Optional[Callable[[_dt.time], Any]] = None,
               label: Optional[str] = None, minute_step: int = 1, style: Any = None):
    """Time field; tap to open a sheet with hour / minute / AM-PM spinners."""
    t = use_theme()
    c = t["colors"]
    open_, set_open = use_state(False)
    cur = value or _dt.time(9, 0)
    draft, set_draft = use_state(cur)

    def shift(field: str, d: int) -> None:
        mins = draft.hour * 60 + draft.minute
        mins += {"h": 60, "m": minute_step, "p": 720}[field] * d
        mins %= 1440
        set_draft(_dt.time(mins // 60, mins % 60))

    def done() -> None:
        set_open(False)
        if on_change:
            on_change(draft)

    return View(
        Label(label) if label else None,
        Pressable(Icon("clock"), Text(_fmt_time(cur), style={"flex": 1, "margin_left": 8, "font_size": 15,
                                                              "color": c["text"]}),
                  on_press=lambda: (set_draft(cur), set_open(True)), accessibility_role="button",
                  style=[_field_box(t, 46), style]),
        Sheet(View(_StepperCol(label="hour", value=0, on_up=lambda: shift("h", 1), on_down=lambda: shift("h", -1), text="%02d" % (draft.hour % 12 or 12)),
                   _StepperCol(label="minute", value=0, on_up=lambda: shift("m", 1), on_down=lambda: shift("m", -1), text="%02d" % draft.minute),
                   _StepperCol(label="period", value=0, on_up=lambda: shift("p", 1), on_down=lambda: shift("p", -1),
                               text="AM" if draft.hour < 12 else "PM"),
                   style={"flex_direction": "row", "justify_content": "center"}),
              _done_button(done), visible=open_, on_close=lambda: set_open(False), title=label or "Select time"))


def _fmt_time(v: _dt.time) -> str:
    return "%02d:%02d %s" % (v.hour % 12 or 12, v.minute, "AM" if v.hour < 12 else "PM")


@component
def Radio(selected: bool = False, label: str = "", on_press: Optional[Callable[[], Any]] = None, size: float = 22,
          style: Any = None):
    c = use_theme()["colors"]
    ring = {"width": size, "height": size, "border_radius": size / 2, "border_width": 2,
            "border_color": c["primary"] if selected else c["border"], "align_items": "center", "justify_content": "center"}
    return Pressable(View(View(style={"width": size / 2, "height": size / 2, "border_radius": size / 4,
                                      "background_color": c["primary"]}) if selected else None, style=ring),
                     Text(label, style={"margin_left": 8, "font_size": 15, "color": c["text"]}) if label else None,
                     on_press=on_press, accessibility_role="radio", accessibility_state={"selected": selected},
                     accessibility_label=label, style=[{"flex_direction": "row", "align_items": "center"}, style])


@component
def RadioGroup(options: Sequence[Any] = (), value: Any = None, on_change: Optional[Callable[[Any], Any]] = None,
               horizontal: bool = True, gap: float = 14, style: Any = None):
    opts = [_opt(o) for o in options]
    return View(*[Radio(selected=o["value"] == value, label=o["label"], key=str(o["value"]),
                        on_press=(lambda v=o["value"]: on_change(v) if on_change else None),
                        style={"margin_right": gap, "margin_bottom": 6} if horizontal else {"margin_bottom": gap})
                  for o in opts],
                style=[{"flex_direction": "row" if horizontal else "column", "flex_wrap": "wrap"}, style])


@component
def Stepper(steps: Sequence[str] = (), current: int = 0, style: Any = None):
    """Progress steps; `current` is the 0-based active step, earlier steps show a check."""
    t = use_theme()
    c = t["colors"]
    n = len(steps)
    cols = []
    for i, name in enumerate(steps):
        done, on = i < current, i == current
        cols.append(View(
            View(style={"flex": 1, "height": 2, "background_color": (c["primary"] if i <= current else c["border"]) if i else "transparent"}),
            View(Text("✓" if done else str(i + 1), style={"font_size": 14, "font_weight": "600",
                                                          "color": c["on_primary"] if (on or done) else c["text_muted"]}),
                 style={"width": 34, "height": 34, "border_radius": 17, "align_items": "center", "justify_content": "center",
                        "background_color": c["primary"] if (on or done) else c["surface_alt"]}),
            View(style={"flex": 1, "height": 2, "background_color": (c["primary"] if i < current else c["border"]) if i < n - 1 else "transparent"}),
            style={"flex": 1, "flex_direction": "row", "align_items": "center"}, key="b%d" % i))
    labels = [Text(name, style={"flex": 1, "text_align": "center", "font_size": 12,
                                "color": c["text"] if i <= current else c["text_muted"]}, key="l%d" % i)
              for i, name in enumerate(steps)]
    return View(View(*cols, style={"flex_direction": "row"}), View(*labels, style={"flex_direction": "row", "margin_top": 6}),
                style=style)


@component
def Alert(message: str = "", title: Optional[str] = None, tone: str = "success", on_close: Optional[Callable[[], Any]] = None,
          style: Any = None):
    """Inline alert / toast body. `tone`: success, warning, danger, primary."""
    t = use_theme()
    c = t["colors"]
    main = c.get(tone, c["primary"])
    glyph = {"success": "success", "warning": "error", "danger": "error"}.get(tone, "info")
    return View(
        View(Icon(glyph, size=14, color=c.get("on_" + tone, "#ffffff")),
             style={"width": 26, "height": 26, "border_radius": 13, "background_color": main, "align_items": "center",
                    "justify_content": "center"}),
        View(Text(title, style={"font_size": 15, "font_weight": "600", "color": c["text"]}) if title else None,
             Text(message, style={"font_size": 13, "color": c["text_muted"]}),
             style={"flex": 1, "margin_horizontal": 10}),
        Pressable(Icon("close", color=c["text_muted"]), on_press=on_close, accessibility_label="Dismiss") if on_close else None,
        style=[{"flex_direction": "row", "align_items": "center", "padding": 12, "border_radius": t["radius"]["md"],
                "border_width": 1, "border_color": main, "background_color": c["surface"]}, style], accessibility_role="alert")


@component
def LabeledCheckbox(value: bool = False, label: str = "", on_value_change: Optional[Callable[[bool], Any]] = None,
                    style: Any = None):
    from .ui import Checkbox
    c = use_theme()["colors"]
    return Pressable(Checkbox(value=value, size=22, color=c["primary"], on_value_change=on_value_change),
                     Text(label, style={"margin_left": 8, "font_size": 15, "color": c["text"]}),
                     on_press=lambda: on_value_change(not value) if on_value_change else None,
                     style=[{"flex_direction": "row", "align_items": "center"}, style])


@component
def TabBar(tabs: Sequence[Dict[str, Any]] = (), value: Any = None, on_change: Optional[Callable[[Any], Any]] = None,
           fab: Optional[Dict[str, Any]] = None, style: Any = None):
    """Bottom bar. `tabs`: `{"key", "label", "icon", "badge"(bool)}`. `fab`: `{"icon", "on_press"}` rendered raised in
    the middle."""
    t = use_theme()
    c = t["colors"]
    items: List[Any] = []
    mid = len(tabs) // 2
    for i, tab in enumerate(tabs):
        if fab is not None and i == mid:
            items.append(View(Pressable(Icon(fab.get("icon", "plus"), size=28, color=c["on_primary"]),
                                        on_press=fab.get("on_press"), accessibility_label=fab.get("label", "Add"),
                                        style={"width": 60, "height": 60, "border_radius": 30, "align_items": "center",
                                               "justify_content": "center", "background_color": c["primary"],
                                               "margin_top": -28, "shadow_color": "#000000", "shadow_opacity": 0.25,
                                               "shadow_radius": 8, "shadow_offset_y": 3, "elevation": 6}),
                              style={"width": 72, "align_items": "center"}, key="fab"))
        on = tab["key"] == value
        col = c["primary"] if on else c["text_muted"]
        items.append(Pressable(
            View(Icon(tab.get("icon", ""), size=22, color=col),
                 View(style={"position": "absolute", "top": -1, "right": -3, "width": 9, "height": 9, "border_radius": 5,
                             "background_color": c["danger"]}) if tab.get("badge") else None),
            Text(tab.get("label", ""), style={"font_size": 11, "margin_top": 3, "color": col}),
            on_press=(lambda k=tab["key"]: on_change(k) if on_change else None), key=str(tab["key"]),
            accessibility_role="tab", accessibility_state={"selected": on},
            style={"flex": 1, "align_items": "center", "justify_content": "center", "padding_vertical": 6}))
    from .env import use_safe_area_insets
    inset = use_safe_area_insets()["bottom"]  # the bar itself paints under the home indicator
    return View(*items, style=[{"flex_direction": "row", "align_items": "center", "height": 62 + inset,
                                "padding_bottom": inset, "background_color": c["surface"], "border_top_width": 1,
                                "border_color": c["border"]}, style])
