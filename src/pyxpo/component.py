from __future__ import annotations

from typing import Any, Callable

from .element import Element, flatten


class Component:
    """A function component. Calling it builds an Element; the fn runs during reconciliation."""

    def __init__(self, fn: Callable[..., Any], name: str = "") -> None:
        self.fn = fn
        self.name = name or getattr(fn, "__name__", "Component")

    def __call__(self, *children: Any, key: Any = None, **props: Any) -> Element:
        return Element(self, props, flatten(children), key)

    def __repr__(self) -> str:
        return "<Component %s>" % self.name


def component(fn: Callable[..., Any]) -> Component:
    return Component(fn)
