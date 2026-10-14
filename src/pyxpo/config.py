from __future__ import annotations

import ast
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


def _mini_parse(text: str) -> Dict[str, Any]:
    """Fallback: reads flat key = literal pairs of the [tool.pyxpo] table only."""
    out: Dict[str, Any] = {}
    inside = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("["):
            inside = line == "[tool.pyxpo]"
            continue
        if inside and "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = ast.literal_eval(v.strip())
    return out


def load_config(project_dir: Path) -> Dict[str, Any]:
    path = Path(project_dir) / "pyproject.toml"
    if not path.is_file():
        raise FileNotFoundError("no pyproject.toml in %s (run inside a pyxpo project)" % project_dir)
    text = path.read_text()
    if _toml is not None:
        cfg = _toml.loads(text).get("tool", {}).get("pyxpo")
    else:
        cfg = _mini_parse(text) or None
    if cfg is None:
        raise ValueError("pyproject.toml has no [tool.pyxpo] table")
    return cfg


def set_requires(project_dir: Path, requires: list) -> None:
    path = Path(project_dir) / "pyproject.toml"
    text = path.read_text()
    line = "requires = [%s]" % ", ".join('"%s"' % r for r in requires)
    if re.search(r"^requires\s*=.*$", text, re.M):
        text = re.sub(r"^requires\s*=.*$", line, text, flags=re.M)
    else:
        text = text.replace("[tool.pyxpo]", "[tool.pyxpo]\n" + line, 1)
    path.write_text(text)
