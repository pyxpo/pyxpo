from __future__ import annotations

from typing import Any

from .._keys import snake_aliases
from . import _env
from ._bridge import Subscription, call

_EVENTS = {"keyboardDidShow": True, "keyboardDidHide": False, "keyboardWillShow": True, "keyboardWillHide": False}


@snake_aliases
class Keyboard:
    @staticmethod
    def dismiss() -> None:
        call("Keyboard", "dismiss")

    @staticmethod
    def addListener(event: str, fn: Any) -> Subscription:
        """`keyboardDidShow` / `keyboardDidHide`; `fn({"endCoordinates": {"height"}})` fires when it flips."""
        if event not in _EVENTS:
            raise ValueError("Keyboard.addListener: one of %s, got %r" % (sorted(_EVENTS), event))
        want = _EVENTS[event]
        last = [bool(_env.current._data["keyboard"]["visible"])]

        def on_env() -> None:
            kb = _env.current._data["keyboard"]
            vis = bool(kb["visible"])
            if vis != last[0]:
                last[0] = vis
                if vis == want:
                    fn({"height": kb["height"], "endCoordinates": {"height": kb["height"]}})

        return Subscription(_env.current.subscribe(on_env))

    @staticmethod
    def isVisible() -> bool:
        return bool(_env.current._data["keyboard"]["visible"])

    @staticmethod
    def metrics() -> Any:
        kb = _env.current._data["keyboard"]
        return {"height": kb["height"]} if kb["visible"] else None
