from __future__ import annotations

from typing import Any, Callable, List, Optional

from .._keys import snake_aliases
from . import _events
from ._bridge import Subscription, call


@snake_aliases
class Linking:
    initial_url: Optional[str] = None  # set by the app when native launched with a deep link
    # URL prefixes a module waits for itself (e.g. a sign-in redirect): the router does not open them as routes.
    claimed: List[str] = []

    @staticmethod
    def is_claimed(url: str) -> bool:
        return any(url.startswith(p) for p in Linking.claimed)

    @staticmethod
    async def openURL(url: str) -> None:
        await call("Linking", "open_url", str(url), reply=True)

    @staticmethod
    async def canOpenURL(url: str) -> bool:
        return bool(await call("Linking", "can_open_url", str(url), reply=True))

    @staticmethod
    async def openSettings() -> None:
        await call("Linking", "open_settings", reply=True)

    @staticmethod
    async def getInitialURL() -> Optional[str]:
        return Linking.initial_url

    @staticmethod
    def addEventListener(event: str, fn: Callable[[Any], Any]) -> Subscription:
        """`fn({"url"})` when the app is opened by a deep link while running."""
        if event != "url":
            raise ValueError("Linking.addEventListener: only 'url', got %r" % (event,))
        return Subscription(_events.on("url", fn))
