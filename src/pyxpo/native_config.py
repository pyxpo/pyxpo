"""Resolves the native app configuration from `[tool.pyxpo]` (see pyxpo.app_config for the schema)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .app_config import resolve as _resolve
from .app_config import safe_name  # noqa: F401  (re-exported)

try:
    import tomllib as _toml  # type: ignore
except ImportError:  # Python < 3.11
    try:
        import tomli as _toml  # type: ignore
    except ImportError:
        _toml = None


def _project_version(project: Path) -> str:
    if _toml is None:
        return ""
    try:
        return str(_toml.loads((Path(project) / "pyproject.toml").read_text()).get("project", {}).get("version", ""))
    except (OSError, ValueError):
        return ""


def resolve(cfg: Dict[str, Any], project: Path) -> Dict[str, Any]:
    """Per-platform native values: top-level identity plus `ios` and `android` sub-dicts, all defaulted."""
    r = _resolve(cfg, project, _project_version(project))
    r["team_id"], r["keystore"], r["key_alias"] = r["ios"]["team_id"], r["android"]["keystore"], r["android"]["key_alias"]
    return r
