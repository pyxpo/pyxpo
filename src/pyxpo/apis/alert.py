from __future__ import annotations

from typing import Any, Dict, List, Optional

from .._keys import snake_aliases
from . import _bridge
from ._bridge import call


def _alert_done(task: Any) -> None:
    if not task.cancelled() and task.exception() is not None:
        _bridge.report(task.exception())


@snake_aliases
class Alert:
    @staticmethod
    def alert(title: str, message: Optional[str] = None, buttons: Optional[List[Dict[str, Any]]] = None,
              options: Optional[Dict[str, Any]] = None) -> Any:
        """Shows a native dialog. `buttons`: `[{"text", "onPress", "style"}]` (at most three on Android).

        Button callbacks run when the dialog closes; `options["onDismiss"]` runs when it is cancelled.
        Returns an awaitable that resolves to the pressed button index (-1 when dismissed).
        """
        items = list(buttons or [{"text": "OK"}])
        labels = [str(b.get("text", "OK")) for b in items]
        opts = options or {}

        async def run() -> int:
            v = int(await call("Alert", "alert", str(title), str(message or ""), labels, reply=True) or 0)
            if 0 <= v < len(items):
                cb = items[v].get("onPress")
            else:
                cb = opts.get("onDismiss")
            if cb is not None:
                r = cb()
                if hasattr(r, "__await__"):
                    await r
            return v

        loop = getattr(_bridge.get_app(), "loop", None)
        if loop is None:
            return run()  # no loop yet (tests / desktop): caller awaits it
        task = loop.create_task(run())
        task.add_done_callback(_alert_done)
        return task
