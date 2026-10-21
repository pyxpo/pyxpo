"""Plays a video file or URL inside the app.

    import pyxpo_video as Video
    from pyxpo import use_ref

    player = use_ref(None)

    Video.VideoView(ref=player, source="/path/clip.mp4", playing=False, controls=True,
                    style={"width": "100%", "aspectRatio": 9 / 16},
                    on_load=lambda info: print(info["duration"], info["width"], info["height"]))

    player.current.play()
    player.current.seek(2.5)

`source` is a local file (a path or a file:// URI) or an http(s) URL. iOS and the Mac (Catalyst) play it with
AVPlayer and its system controls, Android with `android.widget.VideoView` and a `MediaController`, the web and the
desktop window with a `<video>` element.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, Optional
from urllib.parse import unquote, urlparse

from pyxpo import component, use_imperative_handle, use_ref
from pyxpo.module_api import call, native_view, require_linked, view_tag

__version__ = "0.1.0a1"

__all__ = ["VideoView", "VideoViewHandle", "RESIZE_MODES"]

_View = native_view("PxVideoView")

RESIZE_MODES = ("contain", "cover", "stretch")


def _source(value: Any) -> str:
    """A plain file path from a path or a file:// URI; http(s) URLs pass through."""
    if not isinstance(value, str) or not value:
        raise ValueError("source must be a file path, a file:// URI or an http(s) URL, got %r" % (value,))
    if value.startswith("file:"):
        u = urlparse(value)
        if u.netloc not in ("", "localhost"):
            raise ValueError("source must be a local file or an http(s) URL, got %r" % (value,))
        return unquote(u.path)
    if "://" in value and not value.startswith(("http://", "https://")):
        raise ValueError("source must be a local file or an http(s) URL, got %r" % (value,))
    return value


class VideoViewHandle:
    """`ref.current` of a mounted `VideoView`."""

    def __init__(self, view_ref: Any) -> None:
        self._view = view_ref

    def _tag(self) -> int:
        require_linked("Video", "video", package="pyxpo-video")
        tag = view_tag(self._view)
        if tag is None:
            raise RuntimeError("the VideoView is not mounted")
        return tag

    def play(self) -> None:
        """Starts or resumes playback. The `playing` prop wins again the next time it changes."""
        call("Video", "play", self._tag())

    def pause(self) -> None:
        """Pauses playback."""
        call("Video", "pause", self._tag())

    def seek(self, seconds: float) -> None:
        """Jumps to `seconds` from the start."""
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) \
                or seconds < 0:
            raise ValueError("seconds must be a number >= 0, got %r" % (seconds,))
        call("Video", "seek", self._tag(), float(seconds))


@component
def VideoView(source: Optional[str] = None, playing: bool = True, loop: bool = False, muted: bool = False,
              controls: bool = True, resize_mode: str = "contain",
              on_load: Optional[Callable[[Dict[str, Any]], Any]] = None,
              on_error: Optional[Callable[[Dict[str, Any]], Any]] = None,
              on_end: Optional[Callable[[Any], Any]] = None, style: Any = None, **props: Any):
    """A video player sized by `style`. `ref.current` is a `VideoViewHandle`.

    `playing` plays or pauses when it changes; the user can still play and pause with `controls`.
    `on_load(info)` gets `{"duration", "width", "height"}` (seconds, pixels); `on_error(e)` gets `{"message"}`;
    `on_end` fires when a video with `loop=False` reaches its end. `resize_mode` is "contain", "cover" or
    "stretch" (Android always fits the whole video, like "contain")."""
    if resize_mode not in RESIZE_MODES:
        raise ValueError("resize_mode must be one of %s, got %r" % (", ".join(RESIZE_MODES), resize_mode))
    ref = props.pop("ref", None)
    inner = use_ref(None)
    use_imperative_handle(ref, lambda: VideoViewHandle(inner), [])
    wire: Dict[str, Any] = {
        "source": None if source is None else _source(source),
        "playing": bool(playing), "loop": bool(loop), "muted": bool(muted), "controls": bool(controls),
        "resize_mode": resize_mode,
    }
    for name, fn in (("on_load", on_load), ("on_error", on_error), ("on_end", on_end)):
        if fn is not None:
            wire[name] = fn
    return _View(ref=inner, style=style, **wire, **props)
