from __future__ import annotations

import ast
import os
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
    pending = ""  # a value split over lines (a multi-line array), joined until it parses
    for raw in text.splitlines():
        line = raw.strip()
        if pending:
            pending += " " + line
            k, v = pending.split("=", 1)
            try:
                out[k.strip()] = ast.literal_eval(v.strip())
            except SyntaxError:
                continue
            pending = ""
            continue
        if line.startswith("["):
            if line.startswith("[tool.pyxpo."):
                raise ValueError("pyproject.toml uses nested [tool.pyxpo.*] tables: install tomli (pip install tomli) on Python < 3.11")
            inside = line == "[tool.pyxpo]"
            continue
        if inside and "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            try:
                out[k.strip()] = ast.literal_eval(v.strip())
            except SyntaxError:
                if not v.strip().startswith(("[", "{")):
                    raise
                pending = line
    if pending:
        raise ValueError("pyproject.toml: unterminated value in [tool.pyxpo]: %s" % pending.split("=", 1)[0].strip())
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
    from . import app_config
    return app_config.prepare(cfg, project_dir)


def set_requires(project_dir: Path, requires: list) -> None:
    path = Path(project_dir) / "pyproject.toml"
    text = path.read_text()
    line = "requires = [%s]" % ", ".join('"%s"' % r for r in requires)
    if re.search(r"^requires\s*=.*$", text, re.M):
        text = re.sub(r"^requires\s*=.*$", line, text, flags=re.M)
    else:
        text = text.replace("[tool.pyxpo]", "[tool.pyxpo]\n" + line, 1)
    path.write_text(text)


def pip_index_args(cfg: Dict[str, Any], project_dir: Path) -> list:
    """pip args for extra wheel sources: `wheel_index` in [tool.pyxpo], or PYXPO_WHEEL_INDEX (comma-separated).

    http(s) entries become --extra-index-url; anything else is a local dir/file URL for --find-links
    (relative paths resolve against the project dir).
    """
    env = os.environ.get("PYXPO_WHEEL_INDEX")
    entries = [e.strip() for e in env.split(",") if e.strip()] if env else list(cfg.get("wheel_index", []))
    args: list = []
    for e in entries:
        if e.startswith(("http://", "https://")):
            args += ["--extra-index-url", e]
        else:
            p = Path(e[len("file://"):] if e.startswith("file://") else e)
            args += ["--find-links", str(p if p.is_absolute() else (Path(project_dir) / p).resolve())]
    return args
