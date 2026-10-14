from __future__ import annotations

from .._keys import snake_aliases
from . import _env


@snake_aliases
class PixelRatio:
    @staticmethod
    def get() -> float:
        return _env.current._data["scale"]

    @staticmethod
    def getFontScale() -> float:
        return _env.current._data["font_scale"]

    @staticmethod
    def getPixelSizeForLayoutSize(size: float) -> int:
        return int(round(size * _env.current._data["scale"]))

    @staticmethod
    def roundToNearestPixel(size: float) -> float:
        s = _env.current._data["scale"]
        return round(size * s) / s
