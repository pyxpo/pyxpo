"""camelCase -> snake_case name conversion shared by style keys and props (React Native spellings are aliases)."""
from __future__ import annotations

import re
from typing import Dict

_SPLIT = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_SNAKE: Dict[str, str] = {}
# names whose RN spelling does not follow the mechanical rule
_OVERRIDES: Dict[str, str] = {"testID": "test_id", "nativeID": "native_id"}


def to_snake(name: str) -> str:
    """`fontSize` -> `font_size`; names that are already lower case pass through untouched."""
    if name.islower():
        return name
    hit = _SNAKE.get(name)
    if hit is None:
        hit = _OVERRIDES.get(name) or _SPLIT.sub("_", name).lower()
        if len(_SNAKE) > 4096:
            _SNAKE.clear()
        _SNAKE[name] = hit
    return hit
