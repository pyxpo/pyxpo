"""Photo library picker (expo-image-picker shape). Picked files are copied into the app cache, so `uri` is a local path."""
from __future__ import annotations

from typing import Any, Dict

from .._keys import snake_aliases
from ._bridge import call


@snake_aliases
class ImagePicker:
    @staticmethod
    async def launchImageLibraryAsync(allowsMultipleSelection: bool = False, selectionLimit: int = 0) -> Dict[str, Any]:
        """Returns `{"canceled": bool, "assets": [{"uri", "width", "height", "fileSize", "mimeType", "fileName"}]}`.
        `selectionLimit` 0 means no limit (multiple selection only)."""
        res = await call("ImagePicker", "pick", bool(allowsMultipleSelection), int(selectionLimit), reply=True)
        assets = list((res or {}).get("assets") or [])
        return {"canceled": not assets, "assets": assets}
