"""Native entry point: finds the `app/` package next to the code and runs it with file-based routing."""
from __future__ import annotations

import importlib
import os
import runpy

from ..app import run_app
from .discovery import discover, has_routes
from .root import RouterRoot


def main() -> None:
    if os.environ.get("PYXPO_TARGET") == "android":  # before the app imports numpy & co.
        from .. import native_libs
        native_libs.install()
    elif os.environ.get("PYXPO_TARGET") == "ios":  # iOS and the Mac Catalyst desktop app
        from .._internal import apple
        apple.install()
    pkg = importlib.import_module("app")
    app_dir = list(pkg.__path__)[0]
    if not has_routes(app_dir) and os.path.exists(os.path.join(app_dir, "main.py")):
        runpy.run_module("app.main", run_name="__main__")  # legacy single-file app
        return
    run_app(RouterRoot, tree=discover(app_dir), root_dir=app_dir)


if __name__ == "__main__":
    main()
