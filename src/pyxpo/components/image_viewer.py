"""Full-screen image viewer: pinch and double-tap zoom, swipe between images, swipe down to close.

    from pyxpo import ImageViewer

    ImageViewer(images=[{"uri": url} for url in urls], image_index=index, visible=open_,
              on_request_close=lambda: set_open(False))

On iOS and Android the viewer is a native full-screen screen (a UIScrollView per image on iOS, a matrix-zoomed
ImageView in a swipe pager on Android), so zoom, paging and the swipe-down close feel like the system photo viewers.
Android's Back button and iOS's close button call `on_request_close`. On web and desktop it is a Modal with the image
fitted to the window, arrows to page and a close button. Images load from `http(s)://` addresses, local paths,
`file://`, `content://` (Android) and `data:` URIs."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Union

from ..apis._bridge import call, spawn
from ..component import component
from ..hooks import use_effect, use_ref, use_safe_area_insets, use_state
from ..module_api import platform
from ..modules import on_event
from .image import Image
from .modal import Modal
from .pressable import Pressable
from .text import Text
from .view import View

ImageSource = Union[str, Dict[str, Any]]


def _uris(images: Sequence[ImageSource]) -> List[str]:
    """The address of each image: a string, or a source dict with `uri` like `Image(source=...)` takes."""
    if isinstance(images, (str, dict)):
        raise ValueError("images must be a list of sources, like [{'uri': url}]")
    out = []
    for img in images or ():
        uri = img.get("uri") if isinstance(img, dict) else img
        if not isinstance(uri, str) or not uri:
            raise ValueError("each image needs a uri, got %r" % (img,))
        out.append(uri)
    return out


def _options(index: int, count: int, background_color: str, swipe_to_close_enabled: bool,
             double_tap_to_zoom_enabled: bool, max_zoom: float, show_count: bool, close_label: str) -> Dict[str, Any]:
    if isinstance(max_zoom, bool) or not isinstance(max_zoom, (int, float)) or max_zoom < 1:
        raise ValueError("max_zoom must be a number of at least 1")
    return {"index": min(max(int(index or 0), 0), count - 1), "background": str(background_color),
            "swipeToClose": bool(swipe_to_close_enabled), "doubleTapZoom": bool(double_tap_to_zoom_enabled),
            "maxZoom": float(max_zoom), "showCount": bool(show_count), "closeLabel": str(close_label or "Close")}


def _native() -> bool:
    return platform() in ("ios", "android")


@component
def ImageViewer(*, images: Sequence[ImageSource], image_index: int = 0, visible: bool = False,
              on_request_close: Optional[Callable[[], Any]] = None,
              on_image_index_change: Optional[Callable[[int], Any]] = None, background_color: str = "#000000",
              swipe_to_close_enabled: bool = True, double_tap_to_zoom_enabled: bool = True, max_zoom: float = 4.0,
              show_count: bool = True, close_label: str = "Close"):
    """Shows `images` full screen while `visible`, starting at `image_index`.

    The user pinches or double-taps to zoom, swipes sideways to page and swipes down (`swipe_to_close_enabled`) or
    taps the close button to leave; then `on_request_close` runs, and the app sets `visible` back to False.
    `on_image_index_change(index)` runs on each page change. `max_zoom` is the largest zoom, `show_count` shows
    "2 / 5" at the top, `close_label` is the close button's accessibility label."""
    uris = _uris(images)
    opts = _options(image_index, len(uris), background_color, swipe_to_close_enabled, double_tap_to_zoom_enabled,
                    max_zoom, show_count, close_label) if uris else None
    cbs = use_ref(None)
    cbs.current = (on_request_close, on_image_index_change)
    native = _native()

    def present() -> Any:
        if not (visible and native and opts):
            return None
        state = {"open": True}

        def moved(data: Any) -> None:
            fn = cbs.current[1]
            if state["open"] and fn is not None and isinstance(data, dict):
                fn(int(data.get("index") or 0))

        off = on_event("ImageViewer.index", moved)

        async def run() -> None:
            try:
                await call("ImageViewer", "open", uris, opts, reply=True)
            finally:
                off()
                was_open, state["open"] = state["open"], False
            fn = cbs.current[0]
            if was_open and fn is not None:
                fn()

        spawn(run())

        def cleanup() -> None:
            off()
            if state["open"]:  # the app hid it (or unmounted) while it was on screen
                state["open"] = False
                call("ImageViewer", "close")

        return cleanup

    use_effect(present, [visible, native, tuple(uris), tuple(sorted(opts.items())) if opts else None])
    if native or not opts:
        return None
    return Modal(_WebViewer(uris=uris, opts=opts, cbs=cbs) if visible else None, visible=visible, transparent=True,
                 animation_type="fade", on_request_close=lambda: cbs.current[0] and cbs.current[0]())


@component
def _WebViewer(*, uris: List[str], opts: Dict[str, Any], cbs: Any):
    """The web and desktop viewer: one image fitted to the window, arrows to page, a close button."""
    index, set_index = use_state(opts["index"])
    insets = use_safe_area_insets()

    def go(step: int) -> None:
        i = min(max(index + step, 0), len(uris) - 1)
        if i != index:
            set_index(i)
            if cbs.current[1] is not None:
                cbs.current[1](i)

    def close() -> None:
        if cbs.current[0] is not None:
            cbs.current[0]()

    def button(label: str, glyph: str, on_press: Callable[[], Any], style: Dict[str, Any], test_id: str) -> Any:
        return Pressable(Text(glyph, style={"color": "#ffffff", "fontSize": 22, "lineHeight": 26}),
                         on_press=on_press, accessibility_role="button", accessibility_label=label, test_id=test_id,
                         style={"position": "absolute", "width": 44, "height": 44, "borderRadius": 22,
                                "alignItems": "center", "justifyContent": "center",
                                "backgroundColor": "rgba(255,255,255,0.14)", **style})

    top = insets["top"] + 12
    return View(
        Image(source={"uri": uris[index]}, resize_mode="contain", style={"position": "absolute", "top": 0, "left": 0,
                                                                         "right": 0, "bottom": 0}),
        Text("%d / %d" % (index + 1, len(uris)), style={"position": "absolute", "top": top + 12, "alignSelf": "center",
                                                         "color": "#ffffff", "fontSize": 15},
             test_id="image-viewer-count") if opts["showCount"] and len(uris) > 1 else None,
        button(opts["closeLabel"], "✕", close, {"top": top, "left": 16}, "image-viewer-close"),
        button("Previous", "‹", lambda: go(-1), {"left": 16, "top": "50%"}, "image-viewer-prev") if index > 0 else None,
        button("Next", "›", lambda: go(1), {"right": 16, "top": "50%"}, "image-viewer-next")
        if index < len(uris) - 1 else None,
        style={"flex": 1, "backgroundColor": opts["background"]}, test_id="image-viewer",
    )

