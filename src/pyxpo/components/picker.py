"""Picker (`@react-native-picker/picker` API): a field that opens the platform choice dialog."""
from __future__ import annotations

from typing import Any, Callable, List, Optional

from ..apis import _bridge
from ..component import component
from ..element import Element
from .pressable import Pressable
from .text import Text


def PickerItem(label: str = "", value: Any = None, color: Any = None, **props: Any) -> Element:
    """`Picker.Item(label="Java", value="java")`."""
    return Element("PickerItem", {"label": str(label), "value": label if value is None else value, "color": color})


async def _choose(labels: List[str], selected: int, title: str) -> Optional[int]:
    v = await _bridge.call("Picker", "choose", labels, int(selected), str(title), reply=True)
    return None if v is None or int(v) < 0 else int(v)


@component
def Picker(*children: Any, selected_value: Any = None, on_value_change: Optional[Callable[[Any, int], Any]] = None,
           enabled: bool = True, prompt: str = "", style: Any = None, item_style: Any = None, **props: Any):
    """`<Picker selectedValue onValueChange(value, index)>` with `Picker.Item` children. Tapping opens a native
    single-choice dialog (`prompt` is its title)."""
    items = [c.props for c in _flat(children) if isinstance(c, Element) and c.type == "PickerItem"]
    index = next((i for i, it in enumerate(items) if it["value"] == selected_value), -1)
    label = items[index]["label"] if index >= 0 else ""

    async def pick() -> None:
        chosen = await _choose([it["label"] for it in items], index, prompt)
        if chosen is not None and on_value_change is not None:
            on_value_change(items[chosen]["value"], chosen)

    box = {"flex_direction": "row", "align_items": "center", "justify_content": "space-between",
           "min_height": 48, "padding_horizontal": 8, "opacity": 1 if enabled else 0.4}
    return Pressable(Text(label, style=[{"flex": 1, "font_size": 16}, item_style]),
                     Text("▾", style={"font_size": 14}), disabled=not enabled, style=[box, style],
                     on_press=lambda: _bridge.spawn(pick()), accessibility_role="combobox",
                     **{k: v for k, v in props.items() if k in ("test_id", "native_id")})


def _flat(children: Any):
    for c in children:
        if isinstance(c, (list, tuple)):
            yield from _flat(c)
        else:
            yield c


Picker.Item = PickerItem
