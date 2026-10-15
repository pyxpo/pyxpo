"""`Constants`: build-time app info, Expo `expo-constants` shaped (`expo_config`, `extra`, `native_app_version`, ...)."""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from . import _env

_cache: Optional[Dict[str, Any]] = None
_session = uuid.uuid4().hex


def _load() -> Dict[str, Any]:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads((Path(__file__).resolve().parent.parent / "_app_config.json").read_text())
        except (OSError, ValueError):
            _cache = {}  # desktop/dev runs without a build: empty config
    return _cache


class _ConstantsMeta(type):
    @property
    def expo_config(cls) -> Dict[str, Any]:
        return json.loads(json.dumps(_load()))

    @property
    def extra(cls) -> Dict[str, Any]:
        return json.loads(json.dumps(_load().get("extra", {})))

    @property
    def native_app_version(cls) -> Optional[str]:
        return _load().get("version")

    @property
    def native_build_version(cls) -> Optional[str]:
        c = _load()
        if not c:
            return None
        plat = c.get("android" if sys.platform == "android" else "ios", {})
        return str(plat.get("version_code", plat.get("build_number", c.get("build_number"))))

    @property
    def app_name(cls) -> Optional[str]:
        return _load().get("name")

    @property
    def execution_environment(cls) -> str:
        return "bare" if _load() else "unknown"

    @property
    def session_id(cls) -> str:
        return _session

    @property
    def platform(cls) -> str:
        return _env.current._data["os"]


class Constants(metaclass=_ConstantsMeta):
    """Read-only app constants. Everything in `extra` ships in plain text; never put secrets there."""


for _snake, _camel in (("expo_config", "expoConfig"), ("native_app_version", "nativeAppVersion"),
                       ("native_build_version", "nativeBuildVersion"), ("app_name", "appName"),
                       ("execution_environment", "executionEnvironment"), ("session_id", "sessionId")):
    setattr(_ConstantsMeta, _camel, getattr(_ConstantsMeta, _snake))
