from __future__ import annotations

from .._keys import snake_aliases
from ._bridge import call


@snake_aliases
class SplashScreen:
    """expo-splash-screen shape. The splash hides itself after the first render unless `prevent_auto_hide()` ran first."""

    @staticmethod
    def prevent_auto_hide() -> None:
        call("SplashScreen", "prevent_auto_hide")

    @staticmethod
    def hide() -> None:
        call("SplashScreen", "hide")
