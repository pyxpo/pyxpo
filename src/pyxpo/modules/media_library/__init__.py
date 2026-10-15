from __future__ import annotations

from typing import Any, Dict

from ..._keys import snake_aliases
from ...apis._bridge import call
from .. import require_linked


@snake_aliases
class MediaLibrary:
    @staticmethod
    async def requestPermissionsAsync(writeOnly: bool = True) -> Dict[str, Any]:
        require_linked("MediaLibrary", "media-library")
        res = await call("MediaLibrary", "request_permission", bool(writeOnly), reply=True)
        granted = bool((res or {}).get("granted"))
        return {"granted": granted, "status": "granted" if granted else "denied"}

    @staticmethod
    async def saveToLibraryAsync(path: str) -> None:
        """Saves the file's exact bytes to the photo library (no re-encode)."""
        require_linked("MediaLibrary", "media-library")
        await call("MediaLibrary", "save", str(path), reply=True)
