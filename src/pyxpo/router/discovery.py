"""File-based route discovery (expo-router layout rules) for the `app` package.

    app/_layout.py          navigator of the directory (Stack/Tabs/Drawer/Slot)
    app/index.py            "/"
    app/details/[id].py     "/details/:id"
    app/[...rest].py        catch-all
    app/(tabs)/_layout.py   group: no URL segment, own navigator
    app/+not-found.py       shown for unmatched URLs

A directory with `_layout.py` becomes a nested navigator and a screen of its parent; a directory without one is
flattened into its parent (screen name `details/[id]`).
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

from .._internal.modname import module_name_for

Seg = Tuple[str, str]  # (kind "s"|"d"|"c", value)


class RouteError(Exception):
    pass


class Screen:
    """One route entry inside a navigator."""

    def __init__(self, name: str, segments: Tuple[Seg, ...], file: Optional[str], module_name: Optional[str],
                 navigator: Optional["Navigator"] = None, not_found: bool = False) -> None:
        self.name = name
        self.segments = segments
        self.file = file
        self.module_name = module_name
        self.navigator = navigator
        self.not_found = not_found
        self.parent: Optional["Navigator"] = None

    def __repr__(self) -> str:
        return "Screen(%r)" % self.name


class Navigator:
    def __init__(self, path: str, layout_file: Optional[str], layout_module: Optional[str]) -> None:
        self.path = path
        self.layout_file = layout_file
        self.layout_module = layout_module
        self.screens: List[Screen] = []
        self.owner: Optional[Screen] = None

    def screen(self, name: str) -> Optional[Screen]:
        for s in self.screens:
            if s.name == name:
                return s
        return None


class Route:
    """A matchable URL pattern: `chain` goes from a root-navigator screen down to the leaf screen."""

    def __init__(self, chain: List[Screen], segments: Tuple[Seg, ...]) -> None:
        self.chain = chain
        self.segments = segments


class RouteTree:
    def __init__(self, root: Navigator, routes: List[Route], not_found: Optional[List[Screen]], base: str) -> None:
        self.root = root
        self.routes = routes
        self.not_found = not_found
        self.base = base


def parse_segment(part: str) -> Optional[Seg]:
    """URL segment of a path part; None for groups (they add no URL segment)."""
    if part.startswith("(") and part.endswith(")"):
        return None
    if part.startswith("[...") and part.endswith("]"):
        return ("c", part[4:-1])
    if part.startswith("[") and part.endswith("]"):
        return ("d", part[1:-1])
    return ("s", part)


def _segments(rel: str) -> Tuple[Seg, ...]:
    out: List[Seg] = []
    for part in rel.split("/"):
        if part == "index":
            continue
        seg = parse_segment(part)
        if seg is not None:
            out.append(seg)
    return tuple(out)


def _inside(root: str, path: str) -> bool:
    real = os.path.realpath(path)
    return real == root or real.startswith(root + os.sep)


def _scan(root_real: str, directory: str, rel_dir: str, base: str, pkg: str) -> Navigator:
    layout = os.path.join(directory, "_layout.py")
    has_layout = os.path.isfile(layout) and _inside(root_real, layout)
    nav = Navigator(directory, layout if has_layout else None,
                    module_name_for(pkg + "/" + (rel_dir + "/" if rel_dir else "") + "_layout.py") if has_layout else None)
    _collect(root_real, directory, "", nav, base, pkg, rel_dir)
    return nav


def _collect(root_real: str, directory: str, prefix: str, nav: Navigator, base: str, pkg: str, rel_dir: str) -> None:
    for entry in sorted(os.listdir(directory)):
        full = os.path.join(directory, entry)
        if entry.startswith(".") or entry == "__pycache__" or not _inside(root_real, full):
            continue
        rel = prefix + entry
        if os.path.isdir(full):
            if entry.startswith("_"):
                continue  # private folder (helpers, libraries), not routes
            sub_rel = (rel_dir + "/" if rel_dir else "") + entry
            if os.path.isfile(os.path.join(full, "_layout.py")):
                child = _scan(root_real, full, sub_rel, base, pkg)
                scr = Screen(prefix + entry, _segments(prefix + entry), None, None, child)
                child.owner = scr
                scr.parent = nav
                nav.screens.append(scr)
            else:
                _collect(root_real, full, rel + "/", nav, base, pkg, sub_rel)
            continue
        if not entry.endswith(".py") or entry == "__init__.py":
            continue
        stem = entry[:-3]
        if stem == "_layout" or (stem.startswith("_") and stem != "_layout") or stem in ("+html", "+api"):
            continue
        mod = module_name_for(pkg + "/" + (rel_dir + "/" if rel_dir else "") + entry)
        nf = stem == "+not-found"
        scr = Screen(prefix + stem, () if nf else _segments(prefix + stem), full, mod, None, nf)
        scr.parent = nav
        nav.screens.append(scr)


def _flatten(nav: Navigator, chain: List[Screen], segs: Tuple[Seg, ...], out: List[Route],
             nf: List[Optional[List[Screen]]]) -> None:
    for scr in nav.screens:
        if scr.not_found:
            if nf[0] is None:
                nf[0] = chain + [scr]
            continue
        s = segs + scr.segments
        if scr.navigator is not None:
            _flatten(scr.navigator, chain + [scr], s, out, nf)
        else:
            out.append(Route(chain + [scr], s))


def discover(app_dir: str, pkg: str = "app") -> RouteTree:
    """Scan `app_dir` (the `app` package directory) into a RouteTree."""
    root_real = os.path.realpath(app_dir)
    base = os.path.dirname(root_real)
    root = _scan(root_real, root_real, "", base, pkg)
    routes: List[Route] = []
    nf: List[Optional[List[Screen]]] = [None]
    _flatten(root, [], (), routes, nf)
    return RouteTree(root, routes, nf[0], base)


def has_routes(app_dir: str) -> bool:
    """True when `app_dir` holds a `_layout.py` or `index.py` (router mode)."""
    return any(os.path.isfile(os.path.join(app_dir, f)) for f in ("_layout.py", "index.py"))


def load_module(name: str, file: str, root: str) -> Any:
    """Import a route/layout module by file path (names with `[`/`(` are not importable by name).

    Re-uses the module in sys.modules so hot reload, which re-executes in place, keeps one module object.
    """
    real = os.path.realpath(file)
    root_real = os.path.realpath(root)
    if not (real == root_real or real.startswith(root_real + os.sep)):
        raise RouteError("route file outside app root: %s" % file)
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    spec = importlib.util.spec_from_file_location(name, real)
    if spec is None or spec.loader is None:
        raise RouteError("cannot load route %s" % file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return mod


def route_component(mod: Any) -> Any:
    """The screen component of a route module: `default`, else its single `@component`."""
    d = getattr(mod, "default", None)
    if d is not None:
        return d
    from ..component import Component
    comps = [v for k, v in vars(mod).items() if isinstance(v, Component) and not k.startswith("_")
             and getattr(v.fn, "__module__", None) == mod.__name__]
    if len(comps) == 1:
        return comps[0]
    raise RouteError("%s must export `default` (or define exactly one @component)" % getattr(mod, "__name__", mod))
