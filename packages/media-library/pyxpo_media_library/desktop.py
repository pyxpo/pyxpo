"""Desktop backend for `pyxpo run desktop`: the library is a folder, ~/Pictures/pyxpo."""
from __future__ import annotations

import mimetypes
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List


def _dir() -> Path:
    d = Path(os.environ.get("PYXPO_MEDIA_DIR") or Path.home() / "Pictures" / "pyxpo")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _copy(uri: str) -> Path:
    src = Path(uri[7:] if uri.startswith("file://") else uri)
    if not src.is_file():
        raise FileNotFoundError("no such file: %s" % src)
    dst = _dir() / src.name
    if dst.exists():
        dst = dst.with_name("%s-%s%s" % (src.stem, uuid.uuid4().hex[:6], src.suffix))
    shutil.copyfile(src, dst)
    return dst


def create(uri: str) -> Dict[str, Any]:
    dst = _copy(uri)
    video = (mimetypes.guess_type(str(dst))[0] or "").startswith("video/")
    w = h = 0
    if not video:
        try:
            from PIL import Image
            with Image.open(dst) as img:
                w, h = img.size
        except Exception:  # noqa: BLE001
            pass
    return {"id": dst.name, "uri": str(dst), "mediaType": "video" if video else "photo", "width": w, "height": h,
            "duration": 0, "filename": dst.name}


def call(method: str, args: List[Any]) -> Any:
    if method in ("get_permission", "request_permission"):
        return {"status": "granted", "canAskAgain": True, "accessPrivileges": "all"}
    if method == "create":
        return create(args[0])
    if method == "save":
        _copy(args[0])
        return None
    raise ValueError("unknown MediaLibrary method %r" % method)
