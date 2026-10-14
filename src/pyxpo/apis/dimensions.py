from __future__ import annotations

from typing import Any, Callable, Dict

from .._keys import snake_aliases
from . import _env
from ._bridge import Subscription


@snake_aliases
class Dimensions:
    @staticmethod
    def get(which: str = "window") -> Dict[str, float]:
        if which not in ("window", "screen"):
            raise ValueError("Dimensions.get: 'window' or 'screen', got %r" % (which,))
        d = _env.current._data
        return {"width": d[which]["width"], "height": d[which]["height"], "scale": d["scale"],
                "fontScale": d["font_scale"], "font_scale": d["font_scale"]}

    @staticmethod
    def addEventListener(event: str, fn: Callable[[Dict[str, Any]], Any]) -> Subscription:
        """`fn({"window", "screen"})` on every size change. Returns a subscription with `.remove()`."""
        if event != "change":
            raise ValueError("Dimensions.addEventListener: only 'change', got %r" % (event,))
        last = [Dimensions.get("window"), Dimensions.get("screen")]

        def on_env() -> None:
            now = [Dimensions.get("window"), Dimensions.get("screen")]
            if now != last:
                last[:] = now
                fn({"window": now[0], "screen": now[1]})

        return Subscription(_env.current.subscribe(on_env))
