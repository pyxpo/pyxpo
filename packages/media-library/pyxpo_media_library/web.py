"""Web backend for `pyxpo build web`: a page cannot write to the photo library, so saving downloads the file
(it lands in the browser's Downloads folder). The returned asset points at the app's in-memory copy."""
from __future__ import annotations

from typing import Any, List

from pyxpo.renderers.web.browser import download

from . import desktop


def call(method: str, args: List[Any]) -> Any:
    if method in ("get_permission", "request_permission"):
        return {"status": "granted", "canAskAgain": True, "accessPrivileges": "all"}
    if method == "create":
        asset = desktop.create(args[0])
        download(asset["uri"])
        return asset
    if method == "save":
        download(args[0])
        return None
    raise ValueError("unknown MediaLibrary method %r" % method)
