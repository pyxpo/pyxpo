from __future__ import annotations

from typing import Any

from .._keys import snake_aliases
from ._bridge import call


@snake_aliases
class Vibration:
    @staticmethod
    def vibrate(pattern: Any = 400, repeat: bool = False) -> None:
        """`pattern`: milliseconds, or a list `[wait, vibrate, wait, ...]` (Android semantics)."""
        if isinstance(pattern, (list, tuple)):
            call("Vibration", "pattern", [int(x) for x in pattern], bool(repeat))
        else:
            call("Vibration", "vibrate", int(pattern))

    @staticmethod
    def cancel() -> None:
        call("Vibration", "cancel")
