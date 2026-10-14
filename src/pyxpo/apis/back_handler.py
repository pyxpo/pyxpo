from __future__ import annotations

from typing import Any, List

from .._keys import snake_aliases
from . import _bridge
from ._bridge import Subscription, call


class _Back:
    """Registry of hardware-back listeners. The newest listener that returns True consumes the press."""
    handlers: List[Any] = []
    enabled = False

    @classmethod
    def add(cls, fn: Any) -> Any:
        cls.handlers.append(fn)
        cls.sync()

        def remove() -> None:
            if fn in cls.handlers:
                cls.handlers.remove(fn)
            cls.sync()
        return remove

    @classmethod
    def sync(cls) -> None:
        on = bool(cls.handlers)
        if on != cls.enabled and _bridge.get_app() is not None:
            cls.enabled = on
            call("Back", "set_enabled", on)

    @classmethod
    def handle(cls) -> None:
        for fn in reversed(list(cls.handlers)):
            if fn():
                return
        call("Back", "exit")  # nobody consumed it: leave the app


@snake_aliases
class BackHandler:
    @staticmethod
    def addEventListener(event: str, fn: Any) -> Subscription:
        if event != "hardwareBackPress":
            raise ValueError("BackHandler: only 'hardwareBackPress', got %r" % (event,))
        return Subscription(_Back.add(fn))

    @staticmethod
    def exitApp() -> None:
        call("Back", "exit")
