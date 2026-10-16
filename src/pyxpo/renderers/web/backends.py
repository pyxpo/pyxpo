"""Module calls on desktop. Clipboard and Linking are built in; a native module package answers through its
optional `<package>/desktop.py`, which defines `call(method, args)` and runs in a worker thread."""
from __future__ import annotations

import importlib
import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

_lock = threading.Lock()
_mods: Optional[Dict[str, Any]] = None


def _builtin(module: str, method: str, args: List[Any]) -> Any:
    if module == "Clipboard" and method == "set_string":
        subprocess.run(["pbcopy"] if sys.platform == "darwin" else ["xclip", "-selection", "clipboard"],
                       input=str(args[0]).encode(), check=True)
        return None
    if module == "Clipboard" and method == "get_string":
        cmd = ["pbpaste"] if sys.platform == "darwin" else ["xclip", "-selection", "clipboard", "-o"]
        return subprocess.run(cmd, capture_output=True, check=True).stdout.decode()
    if module == "Linking" and method == "open_url":
        import webbrowser
        return bool(webbrowser.open(str(args[0])))
    raise NotImplementedError


def _desktop_modules() -> Dict[str, Any]:
    global _mods
    with _lock:
        if _mods is None:
            found: Dict[str, Any] = {}
            for native, pkg in _linked().items():
                try:
                    found[native] = importlib.import_module(pkg + ".desktop")
                except ImportError:
                    pass
            _mods = found
        return _mods


LINKED_FILE = Path(__file__).resolve().parents[2] / "desktop_modules.json"


def _linked() -> Dict[str, str]:
    """{bridge module name: package}. A built app (Windows) ships the list; the dev tools discover installed ones."""
    if LINKED_FILE.is_file():
        return json.loads(LINKED_FILE.read_text())
    from ...build import autolink
    return {m.native: m.pkg for m in autolink.discover().values()}


def call(module: str, method: str, args: List[Any]) -> Any:
    try:
        return _builtin(module, method, args)
    except NotImplementedError:
        pass
    mod = _desktop_modules().get(module)
    if mod is None:
        raise RuntimeError("native module %r is not available on desktop" % module)
    return mod.call(method, args)
