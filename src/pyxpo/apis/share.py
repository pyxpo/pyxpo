from __future__ import annotations

from typing import Any, Dict, Optional

from .._keys import snake_aliases
from ._bridge import call


@snake_aliases
class Share:
    @staticmethod
    async def share(content: Dict[str, Any], options: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """Opens the system share sheet. `content`: `{"url": path}` or `{"urls": [paths]}`, plus optional `message`.
        Returns `{"action": "sharedAction" | "dismissedAction"}` (Android always reports sharedAction, as react-native does)."""
        urls = list(content.get("urls") or ([content["url"]] if content.get("url") else []))
        if not urls and not content.get("message"):
            raise ValueError("Share.share needs a url, urls or message")
        res = await call("Share", "share", urls, content.get("message") or "", reply=True)
        return {"action": (res or {}).get("action", "dismissedAction")}
