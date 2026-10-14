"""`<Link href=...>` and `<Redirect href=...>`."""
from __future__ import annotations

from typing import Any, Optional

from ..component import component
from ..element import Element
from ..components.pressable import Pressable
from ..components.text import Text
from ..hooks import use_effect
from .hooks import useRouter
from .matching import Href


@component
def Link(*children, href: Href = "/", replace: bool = False, push: bool = False, asChild: bool = False,
         style: Any = None, onPress: Optional[Any] = None):
    """Navigates on press. String children render as `Text`; `asChild=True` makes the single child pressable itself."""
    r = useRouter()

    def go(*_: Any) -> None:
        if onPress is not None and onPress() is False:
            return
        (r.replace if replace else r.push if push else r.navigate)(href)
    if asChild and len(children) == 1 and isinstance(children[0], Element):
        c = children[0]
        return Element(c.type, dict(c.props, onPress=go), c.children, c.key)
    kids = [Text(c, style=style) if isinstance(c, str) else c for c in children]
    return Pressable(*kids, on_press=go, accessibility_role="link", style=None if kids and isinstance(children[0], str) else style)


@component
def Redirect(href: Href = "/"):
    r = useRouter()
    use_effect(lambda: r.replace(href) and None, [str(href)])
    return None
