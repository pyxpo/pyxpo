from __future__ import annotations

from typing import Any, Callable, Optional

from ..component import component
from ._common import ACCENT, accessibility
from .pressable import Pressable
from .text import Text


@component
def Button(title: str = "", on_press: Optional[Callable] = None, color: Any = None, disabled: bool = False,
           accessibility_label: Optional[str] = None, test_id: Optional[str] = None, **props: Any):
    """Minimal platform-styled button (RN `Button`): `title`, `onPress`, `color` (fill), `disabled`."""
    fill = "#dfdfdf" if disabled else (color or ACCENT)
    label = {"color": "#a1a1a1" if disabled else "#ffffff", "font_weight": "500", "font_size": 14,
             "text_align": "center", "text_transform": "uppercase"}
    box = {"background_color": fill, "border_radius": 2, "padding_horizontal": 16, "padding_vertical": 9,
           "min_width": 64, "align_items": "center", "justify_content": "center"}
    extra = {"test_id": test_id} if test_id else {}
    return Pressable(Text(str(title), style=label), on_press=on_press, disabled=disabled, style=box,
                     android_ripple={"color": "#ffffff55"}, accessibility_role="button",
                     accessibility_label=accessibility_label or str(title), **extra, **accessibility(props))
