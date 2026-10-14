from __future__ import annotations

from typing import Any, Dict

from . import _env


class _PlatformMeta(type):
    @property
    def OS(cls) -> str:
        return _env.current._data["os"]

    @property
    def Version(cls) -> Any:
        return _env.current._data.get("os_version")

    @property
    def isTV(cls) -> bool:
        return False

    @property
    def isPad(cls) -> bool:
        return False


class Platform(metaclass=_PlatformMeta):
    """`Platform.OS` ("android" | "ios" | ...), `Platform.select({...})`."""

    @staticmethod
    def select(spec: Dict[str, Any]) -> Any:
        o = _env.current._data["os"]
        if o in spec:
            return spec[o]
        if "native" in spec and o in ("android", "ios"):
            return spec["native"]
        return spec.get("default")
