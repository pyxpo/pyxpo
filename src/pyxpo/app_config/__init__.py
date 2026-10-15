"""Expo-style app configuration: `[tool.pyxpo]` (plus optional app_config.py) resolved into native settings."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Dict

from .resolve import check_assets, resolve, safe_name  # noqa: F401
from .schema import ConfigError, json_schema, normalize, validate  # noqa: F401


def apply_dynamic(cfg: Dict[str, Any], project: Path) -> Dict[str, Any]:
    """Runs `app_config.py`'s `config(cfg) -> dict` on the host, like Expo's app.config.js."""
    f = Path(project) / "app_config.py"
    if not f.is_file():
        return cfg
    spec = importlib.util.spec_from_file_location("_pyxpo_app_config", str(f))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = getattr(mod, "config", None)
    if not callable(fn):
        raise ConfigError("%s must define config(cfg) -> dict" % f)
    out = fn(dict(cfg))
    if not isinstance(out, dict):
        raise ConfigError("%s: config() must return a dict" % f)
    return out


def prepare(cfg: Dict[str, Any], project: Path) -> Dict[str, Any]:
    """Dynamic config, camelCase aliases, then validation. Returns the normalized table."""
    cfg = normalize(apply_dynamic(cfg, project))
    validate(cfg)
    return cfg
