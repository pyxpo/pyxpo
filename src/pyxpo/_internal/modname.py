"""Module naming shared by the router's route loader and the hot reloader."""
from __future__ import annotations

from typing import Optional


def module_name_for(rel: str) -> Optional[str]:
    """`app/(tabs)/[id].py` -> `app.(tabs).[id]`; `app/__init__.py` -> `app`. None for non-.py paths.

    Names with brackets or parentheses are not importable with `import`; the router loads them by file path.
    """
    if not rel.endswith(".py"):
        return None
    name = rel[:-3].replace("/", ".")
    return name[: -len(".__init__")] if name.endswith(".__init__") else name
