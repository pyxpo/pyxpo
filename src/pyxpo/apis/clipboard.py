from __future__ import annotations

from .._keys import snake_aliases
from ._bridge import call


@snake_aliases
class Clipboard:
    @staticmethod
    def setString(text: str) -> None:
        call("Clipboard", "set_string", str(text))

    @staticmethod
    async def getString() -> str:
        return (await call("Clipboard", "get_string", reply=True)) or ""
