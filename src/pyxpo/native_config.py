"""Resolves the native app identity (name, ids, version, signing team) from `[tool.pyxpo]`."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict

try:
    import tomllib as _toml  # type: ignore
except ImportError:  # Python < 3.11
    try:
        import tomli as _toml  # type: ignore
    except ImportError:
        _toml = None


def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", name) or "PyxpoApp"


def _project_version(project: Path) -> str:
    if _toml is None:
        return ""
    try:
        return str(_toml.loads((Path(project) / "pyproject.toml").read_text()).get("project", {}).get("version", ""))
    except (OSError, ValueError):
        return ""


def resolve(cfg: Dict[str, Any], project: Path) -> Dict[str, Any]:
    """Native values shared by both platforms. Defaults match what `pyxpo create` writes."""
    name = str(cfg.get("name") or Path(project).name)
    bundle_id = str(cfg.get("bundle_id", "com.example.app"))
    ios = cfg.get("ios") or {}
    android = cfg.get("android") or {}
    return {
        "name": name,
        "product_name": safe_name(name),
        "bundle_id": bundle_id,
        "scheme": str(cfg.get("scheme") or bundle_id),
        "version": str(cfg.get("version") or _project_version(project) or "1.0.0"),
        "build_number": int(cfg.get("build_number", 1)),
        "team_id": str(ios.get("team_id", "")),
        "keystore": str(android.get("keystore", "")),
        "key_alias": str(android.get("key_alias", "")),
    }
