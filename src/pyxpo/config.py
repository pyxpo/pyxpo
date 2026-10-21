from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def load_config(project_dir: Path, mode: Optional[str] = None) -> Dict[str, Any]:
    """The validated `[tool.pyxpo]` table. `mode` (default `module_hooks.build_mode()`) is passed to module build
    hooks; builders pass `build_mode(release)`. Data the hooks ship is kept under `MODULE_DATA` for the app config."""
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
    from . import app_config, module_hooks
    from .app_config.resolve import MODULE_DATA
    mode = module_hooks.check_mode(mode) if mode else module_hooks.build_mode()
    cfg, shipped = module_hooks.run(cfg, Path(project_dir), mode)
    cfg = app_config.prepare(cfg, project_dir, mode)
    if shipped:
        cfg[MODULE_DATA] = shipped
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


_PACKAGE_DIR = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def app_dirs(cfg: Dict[str, Any], project_dir: Path) -> List[str]:
    """The project folders an app ships: app/, assets/ and each `include` folder of [tool.pyxpo] (more top-level
    Python packages, for example a library the app shares with a command-line tool)."""
    extra = []
    for name in cfg.get("include", []):
        if not _PACKAGE_DIR.match(name) or name in ("app", "assets", "pyxpo"):
            raise ValueError("[tool.pyxpo] include: %r is not a top-level package folder name" % name)
        if not (Path(project_dir) / name).is_dir():
            raise FileNotFoundError("[tool.pyxpo] include: no folder %r in %s" % (name, project_dir))
        extra.append(name)
    return ["app", "assets"] + extra


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
