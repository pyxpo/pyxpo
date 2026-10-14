from __future__ import annotations

from typing import Any, Callable, Optional

from ..animated import Animated, use_animated_value
from ..component import component
from ..element import _host
from ..hooks import use_effect, use_memo, use_ref, use_state, use_window_dimensions
from .view import View

_Modal = _host("Modal")


@component
def Modal(*children: Any, visible: bool = True, animation_type: str = "none", transparent: bool = False,
          on_request_close: Optional[Callable[[], Any]] = None, on_show: Optional[Callable[[], Any]] = None,
          on_dismiss: Optional[Callable[[], Any]] = None, style: Any = None, **props: Any):
    """Layer above the whole app. `animationType`: none | fade | slide. Android back fires `onRequestClose`;
    `onShow` runs once the layer is on screen, `onDismiss` after it is gone. A non-transparent modal has a
    dimmed backdrop."""
    animated = animation_type in ("fade", "slide")
    mounted, set_mounted = use_state(bool(visible))
    p = use_animated_value(1.0 if visible else 0.0)
    h = use_window_dimensions()["height"]
    first = use_ref(True)
    cbs = use_ref(None)
    cbs.current = (on_show, on_dismiss)
    duration = 250

    def run() -> None:
        if first.current:
            first.current = False
            return
        if not animated:  # keep state in sync so a later switch to fade/slide does not flash a stale layer
            set_mounted(bool(visible))
            p.set_value(1.0 if visible else 0.0)
            return
        if visible:
            set_mounted(True)
            Animated.timing(p, 1.0, duration=duration).start()
        else:  # unmount only when the fade-out ran to the end; an interrupted one means `visible` came back
            Animated.timing(p, 0.0, duration=duration).start(
                lambda r: set_mounted(False) if r.get("finished") else None)

    use_effect(run, [bool(visible), animated])
    slide_y = use_memo(lambda: p.interpolate([0, 1], [h, 0]), [h])  # one node per height, not per render
    show = (mounted or visible) if animated else bool(visible)

    shown_before = use_ref(False)

    def notify() -> None:
        on_show_cb, on_dismiss_cb = cbs.current
        if show and not shown_before.current and on_show_cb is not None:
            on_show_cb()
        if not show and shown_before.current and on_dismiss_cb is not None:
            on_dismiss_cb()
        shown_before.current = show

    use_effect(notify, [show])
    if not show:
        return None
    fill = {"flex": 1, "background_color": "transparent" if transparent else "rgba(0,0,0,0.5)"}
    if animation_type == "fade":
        fill["opacity"] = p
    box: Any = {"flex": 1}
    if animation_type == "slide":
        box = {"flex": 1, "transform": [{"translate_y": slide_y}]}
    inner = View(*children, style=[box, style], **props)
    return _Modal(View(inner, style=fill), on_request_close=on_request_close,
                  style={"position": "absolute", "left": 0, "top": 0, "right": 0, "bottom": 0})
