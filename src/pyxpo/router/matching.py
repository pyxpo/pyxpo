"""URL matching: href -> route chain + params (static > dynamic > catch-all)."""
from __future__ import annotations

import posixpath
import re
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import parse_qsl, quote, unquote, urlencode

from .discovery import Route, RouteTree, Screen

Href = Union[str, Dict[str, Any]]
_RANK = {"s": 0, "d": 1, "c": 2}


class Match:
    def __init__(self, chain: List[Screen], params: Dict[str, Any], query: Dict[str, Any], pathname: str,
                 found: bool = True) -> None:
        self.chain = chain
        self.params = params          # path params (str, or list of str for catch-all)
        self.query = query            # unused params / query string
        self.pathname = pathname      # URL path without groups, e.g. "/user/42"
        self.found = found

    @property
    def all_params(self) -> Dict[str, Any]:
        out = dict(self.query)
        out.update(self.params)
        return out


def _str(v: Any) -> Any:
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    return str(v)


def resolve(href: Href, current: str = "/") -> Tuple[str, Dict[str, Any]]:
    """Normalize an href into (absolute pathname, extra query params)."""
    query: Dict[str, Any] = {}
    if isinstance(href, dict):
        path = str(href.get("pathname", ""))
        params = dict(href.get("params") or {})

        def sub(m: "re.Match[str]") -> str:
            key = m.group(2)
            if key not in params:
                return m.group(0)
            v = params.pop(key)
            if isinstance(v, (list, tuple)):
                return "/".join(quote(str(x), safe="") for x in v)
            return quote(str(v), safe="")

        path = re.sub(r"\[(\.\.\.)?([^\]/]+)\]", sub, path)
        for k, v in params.items():
            query[k] = _str(v)
        path, _, qs = path.partition("?")
    else:
        path = str(href)
        path, _, qs = path.partition("?")
    qs = qs.partition("#")[0]
    path = path.partition("#")[0]
    for k, v in parse_qsl(qs, keep_blank_values=True):
        if k in query and isinstance(query[k], str):
            query[k] = [query[k], v]
        elif k in query:
            query[k].append(v)
        else:
            query[k] = v
    if not path.startswith("/"):
        base = current if current.endswith("/") or not current else posixpath.dirname(current)
        path = posixpath.join(base or "/", path)
    path = posixpath.normpath(path)
    if not path.startswith("/"):
        path = "/" + path
    if path.startswith("//"):
        path = "/" + path.lstrip("/")
    # groups in a typed href are tolerated: "/(tabs)/home" -> "/home"
    parts = [p for p in path.split("/") if p and not (p.startswith("(") and p.endswith(")"))]
    return "/" + "/".join(parts), query


def _try(route: Route, parts: List[str]) -> Optional[Dict[str, Any]]:
    segs = route.segments
    params: Dict[str, Any] = {}
    i = 0
    for n, (kind, val) in enumerate(segs):
        if kind == "c":
            rest = parts[i:]
            if not rest:
                return None
            params[val] = [unquote(p) for p in rest]
            return params
        if i >= len(parts):
            return None
        if kind == "s":
            if parts[i] != val:
                return None
        else:
            params[val] = unquote(parts[i])
        i += 1
    return params if i == len(parts) else None


def match(tree: RouteTree, href: Href, current: str = "/") -> Match:
    path, query = resolve(href, current)
    parts = [p for p in path.split("/") if p]
    best: Optional[Tuple[Tuple[int, ...], int, Route, Dict[str, Any]]] = None
    for order, r in enumerate(tree.routes):
        p = _try(r, parts)
        if p is None:
            continue
        key = tuple(_RANK[k] for k, _ in r.segments)
        if best is None or (key, order) < (best[0], best[1]):
            best = (key, order, r, p)
    if best is None:
        return Match(list(tree.not_found or []), {"+not-found": parts}, query, path, found=False)
    return Match(best[2].chain, best[3], query, path)


def build_href(pathname: str, params: Dict[str, Any]) -> str:
    qs = urlencode([(k, v) for k, vs in params.items() for v in (vs if isinstance(vs, list) else [vs])])
    return pathname + ("?" + qs if qs else "")
