"""Device photo library: permissions and saving photos and videos (expo-media-library shape)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from pyxpo.module_api import call, permission_response, require_linked, snake_aliases

__version__ = "0.1.0"

_PRIVILEGES = ("all", "limited", "none")


def _linked() -> None:
    require_linked("MediaLibrary", "media-library", package="pyxpo-media-library")


def _local(uri: Any) -> str:
    if not isinstance(uri, str) or not uri:
        raise ValueError("uri must be a non-empty local file path")
    if "://" in uri and not uri.startswith("file://"):
        raise ValueError("uri must be a local file path or file:// URL, got %r" % (uri,))
    return uri


def _permission(res: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    res = res or {}
    out = permission_response(str(res.get("status", "denied")), bool(res.get("canAskAgain", False)))
    priv = res.get("accessPrivileges")
    out["accessPrivileges"] = priv if priv in _PRIVILEGES else ("all" if out["granted"] else "none")
    return out


@snake_aliases
class MediaLibrary:
    @staticmethod
    async def getPermissionsAsync(writeOnly: bool = False) -> Dict[str, Any]:
        """Expo `PermissionResponse` plus `accessPrivileges` (`"all"`, `"limited"` or `"none"`), without asking.
        `writeOnly=True` covers only adding to the library (`saveToLibraryAsync`, `createAssetAsync`)."""
        _linked()
        return _permission(await call("MediaLibrary", "get_permission", bool(writeOnly), reply=True))

    @staticmethod
    async def requestPermissionsAsync(writeOnly: bool = False) -> Dict[str, Any]:
        """Asks for photo library access when it is still undetermined. A user who allowed only some photos gets
        `granted` with `accessPrivileges == "limited"`. Adding needs no permission on Android 10+."""
        _linked()
        return _permission(await call("MediaLibrary", "request_permission", bool(writeOnly), reply=True))

    @staticmethod
    async def createAssetAsync(uri: str) -> Dict[str, Any]:
        """Adds a local photo or video to the library with its exact bytes and returns the new asset
        `{"id", "uri", "mediaType": "photo"|"video", "width", "height", "duration", "filename"}` (`duration` in seconds,
        0 for photos). `uri` is `ph://<id>` on iOS and a `content://` URI on Android. Needs write access only."""
        _linked()
        res = await call("MediaLibrary", "create", _local(uri), reply=True)
        return dict(res or {})

    @staticmethod
    async def saveToLibraryAsync(localUri: str) -> None:
        """Saves the photo or video's exact bytes to the library (no re-encode)."""
        _linked()
        await call("MediaLibrary", "save", _local(localUri), reply=True)
