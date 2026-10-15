"""Terminal output helpers for the CLI: check marks, dim hints and colour when stdout is a terminal."""
from __future__ import annotations

import os
import sys


def _color() -> bool:
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb"


def _paint(code: str, text: str) -> str:
    return "\033[%sm%s\033[0m" % (code, text) if _color() else text


def bold(text: str) -> str:
    return _paint("1", text)


def dim(text: str) -> str:
    return _paint("2", text)


def cyan(text: str) -> str:
    return _paint("36", text)


def ok(msg: str) -> None:
    print("%s %s" % (_paint("32", "✔"), msg))


def warn(msg: str) -> None:
    print("%s %s" % (_paint("33", "⚠"), msg))


def item(msg: str, hint: str = "", width: int = 0) -> None:
    """One `›` line, with an optional dim hint aligned at `width`."""
    line = "  %s %s" % (dim("›"), cyan(msg.ljust(width)) if hint else cyan(msg))
    print(line + ("  " + dim(hint) if hint else ""))
