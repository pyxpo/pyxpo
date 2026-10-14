"""camelCase -> snake_case name conversion shared by style keys and props (React Native spellings are aliases)."""
from __future__ import annotations

import re
from typing import Any, Dict

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


# RN prop names that map to a differently named pyxpo prop (everything else follows to_snake)
PROP_OVERRIDES: Dict[str, str] = {
    "placeholderTextColor": "placeholder_color", "returnKeyType": "return_key", "secureTextEntry": "secure",
    "viewBox": "viewbox", "testID": "test_id", "nativeID": "native_id",
}


def prop_name(k: str) -> str:
    return k if k.islower() else (PROP_OVERRIDES.get(k) or to_snake(k))


def alias_props(props: Dict[str, Any]) -> Dict[str, Any]:
    """Converts camelCase prop names to the snake_case ones. Giving both spellings raises like a duplicate kwarg."""
    out: Dict[str, Any] = {}
    for k, v in props.items():
        n = prop_name(k)
        if n in out or (n != k and n in props):
            raise TypeError("got both %r and %r" % (k, n))
        out[n] = v
    return out


def snake_aliases(cls: Any) -> Any:
    """Gives every camelCase static method of `cls` a snake_case twin (`addEventListener` -> `add_event_listener`)."""
    for name, val in list(vars(cls).items()):
        if not name.startswith("_") and not name.islower() and isinstance(val, (staticmethod, classmethod)):
            setattr(cls, to_snake(name), val)
    return cls
