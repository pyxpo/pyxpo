"""Module build hooks: host-side code of a linked module that runs while pyxpo loads `[tool.pyxpo]`.

A module opts in with `"build": {"hook": "its_package.sub:function"}` in its pyxpo-module.json. The hook runs on
the build machine, never inside the app, each time `pyxpo build`, `run`, `stage`, `prebuild` or `config` loads the
config: after pyproject.toml is read and before `app_config.py` and validation. It gets a `BuildContext` and can

- edit `ctx.config` (the raw `[tool.pyxpo]` table) in place, or return a new table,
- ship JSON data into the app with `ctx.ship(data)`, read back at runtime with `pyxpo.modules.build_data(name)`,
- stop the build with `ctx.fail(msg)` (or by raising `ValueError`), or print `ctx.warn(msg)` once per process.

`ctx.mode` is the build mode: `PYXPO_MODE` (`--mode`) when set, else `production` for release builds and
`development` otherwise. pyxpo-dot-env uses all of this to load `.env` files.
"""
from __future__ import annotations

import importlib
import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .app_config.schema import ConfigError

MODE_ENV = "PYXPO_MODE"
MODE_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
# `pyxpo run desktop --preview` runs the app in this process, without a staged `_app_config.json`.
DATA_ENV = "PYXPO_MODULE_DATA"
_warned: Set[Tuple[str, str]] = set()


def build_mode(release: bool = False) -> str:
    """`PYXPO_MODE` when set (for example `staging`), else `production` for release builds, else `development`."""
    return check_mode(os.environ.get(MODE_ENV, "").strip() or ("production" if release else "development"))


def check_mode(mode: str) -> str:
    # The mode becomes part of file names such as `.env.<mode>`, so it is held to a plain word.
    if not isinstance(mode, str) or not MODE_RE.match(mode):
        raise ConfigError("build mode %r must be lowercase letters, digits and dashes (for example staging)" % (mode,))
    return mode


class BuildContext:
    """What a module build hook gets. `config` is the raw `[tool.pyxpo]` table (keys as written in pyproject.toml)."""

    def __init__(self, name: str, project: Path, mode: str, config: Dict[str, Any]) -> None:
        self.name, self.project, self.mode, self.config = name, Path(project), mode, config
        self.shipped: Optional[Any] = None

    @property
    def options(self) -> Dict[str, Any]:
        """This module's `[tool.pyxpo.module_options.<name>]` table (empty when there is none)."""
        opts = self.config.get("module_options", self.config.get("moduleOptions")) or {}
        mine = opts.get(self.name) if isinstance(opts, dict) else None
        return mine if isinstance(mine, dict) else {}

    def ship(self, data: Any) -> None:
        """Bundles `data` (JSON) into the app as `pyxpo.modules.build_data(<module name>)`. Everything shipped
        can be read by anyone who has the app, so never ship secrets."""
        try:
            json.dumps(data)
        except (TypeError, ValueError) as e:
            raise ConfigError("module %r: ship() needs JSON data (%s)" % (self.name, e))
        self.shipped = data

    def warn(self, msg: str) -> None:
        """Prints a warning once per process (the config is loaded several times in one build)."""
        if (self.name, msg) not in _warned:
            _warned.add((self.name, msg))
            from . import term
            term.warn("%s: %s" % (self.name, msg))

    def fail(self, msg: str) -> None:
        raise ConfigError("%s: %s" % (self.name, msg))


def _hook(module: Any, spec: str) -> Callable[[BuildContext], Any]:
    path, _, attr = spec.partition(":")
    if path != module.pkg and not path.startswith(module.pkg + "."):
        raise ConfigError("module %r: build.hook %r must live in its own package %s" % (module.name, spec, module.pkg))
    fn = getattr(importlib.import_module(path), attr, None)
    if not callable(fn):
        raise ConfigError("module %r: build.hook %r is not a function" % (module.name, spec))
    return fn


def run(cfg: Dict[str, Any], project: Path, mode: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Runs the build hooks of the modules `cfg` lists, in list order. Returns (config, {module: shipped data})."""
    from .build import autolink

    listed: List[str] = cfg.get("modules") or []
    if not isinstance(listed, list) or not all(isinstance(n, str) for n in listed):
        return cfg, {}  # resolve() reports the bad list
    found = autolink.find(listed)
    shipped: Dict[str, Any] = {}
    for name in listed:
        m = found.get(name)
        spec = ((m.meta.get("build") or {}).get("hook") if m else None) or ""
        if not spec or name in shipped:
            continue
        ctx = BuildContext(name, project, mode, cfg)
        try:
            out = _hook(m, spec)(ctx)
        except ValueError:
            raise
        except Exception as e:  # noqa: BLE001
            raise ConfigError("module %r build hook %s failed: %s: %s" % (name, spec, type(e).__name__, e))
        if out is not None:
            if not isinstance(out, dict):
                raise ConfigError("module %r build hook must return None or the config table" % name)
            cfg = out
        if ctx.shipped is not None:
            shipped[name] = ctx.shipped
    return cfg, shipped
