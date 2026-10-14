from __future__ import annotations

from typing import Any, Callable, Optional

from .._keys import snake_aliases
from . import _env
from ._bridge import Subscription


@snake_aliases
class Appearance:
    @staticmethod
    def getColorScheme() -> Optional[str]:
        return _env.current._data["color_scheme"]

    @staticmethod
    def addChangeListener(fn: Callable[[Any], Any]) -> Subscription:
        """`fn({"colorScheme"})` when the system light/dark setting flips."""
        last = [Appearance.getColorScheme()]

        def on_env() -> None:
            now = Appearance.getColorScheme()
            if now != last[0]:
                last[0] = now
                fn({"colorScheme": now})

        return Subscription(_env.current.subscribe(on_env))
