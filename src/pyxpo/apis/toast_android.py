from __future__ import annotations

from .._keys import snake_aliases
from ._bridge import call


@snake_aliases
class ToastAndroid:
    SHORT = 0
    LONG = 1
    TOP = 49
    BOTTOM = 81
    CENTER = 17

    @staticmethod
    def show(message: str, duration: int = 0) -> None:
        """Shows the platform toast (android.widget.Toast)."""
        call("Toast", "show", str(message), bool(duration))

    @staticmethod
    def showWithGravity(message: str, duration: int, gravity: int) -> None:
        call("Toast", "show", str(message), bool(duration))
