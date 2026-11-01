from __future__ import annotations

from typing import Any, Dict, List, Optional

from .._keys import snake_aliases
from . import _bridge
from ._bridge import Subscription, call


class _Back:
    """Registry of hardware-back listeners. The newest listener that returns True consumes the press."""
    handlers: List[Any] = []
    # handler -> predicate saying whether it would consume Back now. A handler without one always might.
    can: Dict[Any, Any] = {}
    enabled = False

    @classmethod
    def add(cls, fn: Any, can: Optional[Any] = None) -> Any:
        """`can`, when given, lets the native side leave Back to the system (predictive back-to-home, app exit)
        whenever no handler would take it. Call `sync` again when its answer may have changed."""
        cls.handlers.append(fn)
        if can is not None:
            cls.can[fn] = can
        cls.sync()

        def remove() -> None:
            if fn in cls.handlers:
                cls.handlers.remove(fn)
            if fn not in cls.handlers:
                cls.can.pop(fn, None)
            cls.sync()
        return remove

    @classmethod
    def sync(cls) -> None:
        on = any(cls.can[fn]() if fn in cls.can else True for fn in cls.handlers)
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
