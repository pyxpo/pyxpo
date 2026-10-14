from __future__ import annotations

import os
from typing import Any

from .._keys import alias_props
from ..component import component
from ..element import Element
from .view import View


def Image(*children: Any, key: Any = None, **props: Any) -> Element:
    """Image from `source`: a path, an http(s) URL, a data: URI, `asset:name`, or `{"uri": ...}`.
    RN props: resizeMode, tintColor (style), onLoad, onError, onLoadStart, onLoadEnd, blurRadius, fadeDuration."""
    if props and not "".join(props).islower():
        props = alias_props(props)
    src = props.get("source")
    if isinstance(src, str):
        src = {"uri": src}
    if isinstance(src, dict) and isinstance(src.get("uri"), str):
        uri = src["uri"]
        if "://" not in uri and not uri.startswith(("data:", "asset:", "/")):
            uri = os.path.abspath(uri)
        src = dict(src, uri=uri)
    if src is not None:
        props["source"] = src
    return Element("Image", props, [], key)


@component
def ImageBackground(*children: Any, source: Any = None, style: Any = None, image_style: Any = None,
                    resize_mode: Any = None, **props: Any):
    """Image drawn behind its children (RN `ImageBackground`)."""
    fill = {"position": "absolute", "left": 0, "top": 0, "right": 0, "bottom": 0}
    img = Image(source=source, style=[fill, image_style], **({"resize_mode": resize_mode} if resize_mode else {}))
    return View(img, *children, style=style, **props)
