"""Applies file updates pushed by the dev server: re-executes changed app modules, then re-renders."""
from __future__ import annotations

import ast
import base64
import hashlib
import os
import sys
import traceback
import types
from typing import Any, Dict, List, Optional, Set

import importlib

app_mod = importlib.import_module("pyxpo.app")
comp_mod = importlib.import_module("pyxpo.component")
module_name_for = importlib.import_module("pyxpo._internal.modname").module_name_for

PKG = "app"


def _safe_path(base: str, rel: str) -> str:
    """Resolve rel under base/app only; reject traversal and absolute paths."""
    if not rel or os.path.isabs(rel) or "\\" in rel:
        raise ValueError("bad path %r" % rel)
    parts = rel.split("/")
    if parts[0] != PKG or ".." in parts or "" in parts:
        raise ValueError("bad path %r" % rel)
    path = os.path.normpath(os.path.join(base, *parts))
    root = os.path.normpath(os.path.join(base, PKG))
    if os.path.commonpath([path, root]) != root:
        raise ValueError("bad path %r" % rel)
    return path


_module_name = module_name_for


def _sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


class HotReloader:
    def __init__(self, app: Any, base: str, entry: Optional[str] = None) -> None:
        self.app = app
        self.base = os.path.realpath(base)
        root = os.path.join(self.base, PKG)
        entry = os.path.realpath(entry) if entry else None
        # Only an entry inside the app package is re-executed (legacy app/main.py); the router entry lives in
        # pyxpo itself and re-renders its live RouterRoot instead.
        self.entry = entry if entry and entry.startswith(root + os.sep) else None
        self.loaded: Dict[str, str] = {}
        for dp, dns, fns in os.walk(root):
            dns[:] = [d for d in dns if d != "__pycache__" and not d.startswith(".")]
            for fn in fns:
                if fn.startswith("."):
                    continue
                full = os.path.join(dp, fn)
                rel = os.path.relpath(full, self.base).replace(os.sep, "/")
                with open(full, "rb") as f:
                    self.loaded[rel] = _sha1(f.read())

    # -- public --------------------------------------------------------
    def apply(self, update: Dict[str, Any]) -> bool:
        """Apply {"files": {rel: {"sha1","data"(b64)}}, "deleted": [rel]}. Returns True on success."""
        try:
            return self._apply(update)
        except Exception as e:  # noqa: BLE001
            self._report("reload failed", e)
            return False

    # -- internals -----------------------------------------------------
    def _report(self, what: str, exc: BaseException) -> None:
        text = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stderr)
        self.app.show_error("%s\n%s" % (what, text))

    def _apply(self, update: Dict[str, Any]) -> bool:
        changed: Dict[str, bytes] = {}
        for rel, meta in update.get("files", {}).items():
            _safe_path(self.base, rel)
            if self.loaded.get(rel) == meta["sha1"]:
                continue
            changed[rel] = base64.b64decode(meta["data"])
        deleted = [r for r in update.get("deleted", []) if r in self.loaded]
        for rel in deleted:
            _safe_path(self.base, rel)
        if not changed and not deleted:
            return True
        # Compile everything first: a syntax error must change nothing.
        for rel, data in changed.items():
            if rel.endswith(".py"):
                try:
                    compile(data, _safe_path(self.base, rel), "exec")
                except SyntaxError as e:
                    self._report("syntax error in %s" % rel, e)
                    return False
        for rel, data in changed.items():
            self._write(rel, data)
            self.loaded[rel] = _sha1(data)
        for rel in deleted:
            self._remove(rel)
            self.loaded.pop(rel, None)
        names = {n for n in (_module_name(r) for r in list(changed) + deleted) if n}
        err = self._reexec(names, [n for n in (_module_name(r) for r in deleted) if n])
        if err is not None:
            self._report("error while reloading", err)
            return False
        root = app_mod._hot.captured
        app_mod._hot.captured = None
        err = self.app.hot_refresh(root)
        if err is not None:
            self._report("error while rendering", err)
            return False
        return True

    def _write(self, rel: str, data: bytes) -> None:
        path = _safe_path(self.base, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".pyxpo-tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        pyc_dir = os.path.join(os.path.dirname(path), "__pycache__")
        stem = os.path.basename(path)[:-3] + "."
        if os.path.isdir(pyc_dir):
            for fn in os.listdir(pyc_dir):
                if fn.startswith(stem) and fn.endswith(".pyc"):
                    try:
                        os.remove(os.path.join(pyc_dir, fn))
                    except OSError:
                        pass

    def _remove(self, rel: str) -> None:
        try:
            os.remove(_safe_path(self.base, rel))
        except OSError:
            pass

    def _loaded_modules(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        prefix = self.base + os.sep
        for name, mod in list(sys.modules.items()):
            f = getattr(mod, "__file__", None)
            if f and (name == PKG or name.startswith(PKG + ".")):
                f = os.path.realpath(f)
                if f.startswith(prefix) and f.endswith(".py"):
                    out[name] = f
        return out

    def _imports(self, name: str, path: str, known: Set[str]) -> Set[str]:
        try:
            with open(path, "rb") as f:
                tree = ast.parse(f.read(), path)
        except (OSError, SyntaxError):
            return set()
        pkg = name if os.path.basename(path) == "__init__.py" else name.rpartition(".")[0]
        deps: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                deps.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    parts = pkg.split(".") if pkg else []
                    parts = parts[: len(parts) - (node.level - 1)]
                    mod = ".".join(parts + ([node.module] if node.module else []))
                else:
                    mod = node.module or ""
                deps.add(mod)
                deps.update("%s.%s" % (mod, a.name) for a in node.names)
        return {d for d in deps if d in known and d != name}

    def _plan(self, loaded: Dict[str, str], changed: Set[str]) -> List[str]:
        graph = {n: self._imports(n, p, set(loaded)) for n, p in loaded.items()}
        todo = set(n for n in changed if n in loaded)
        grew = True
        while grew:  # add transitive dependents
            grew = False
            for n, deps in graph.items():
                if n not in todo and deps & todo:
                    todo.add(n)
                    grew = True
        order: List[str] = []
        seen: Set[str] = set()

        def visit(n: str) -> None:
            if n in seen:
                return
            seen.add(n)
            for d in sorted(graph.get(n, ())):
                if d in todo:
                    visit(d)
            order.append(n)

        for n in sorted(todo):
            visit(n)
        return order

    def _reexec(self, changed: Set[str], deleted: List[str]) -> Optional[BaseException]:
        loaded = self._loaded_modules()
        jobs = [(n, loaded[n]) for n in self._plan(loaded, changed) if n not in deleted]
        if self.entry:
            entry_name = _module_name(os.path.relpath(self.entry, self.base).replace(os.sep, "/")) or "app.main"
            if entry_name not in [n for n, _ in jobs]:
                jobs.append((entry_name, self.entry))
        saved_mods = dict(sys.modules)
        saved_attrs: List[Any] = []
        for n in deleted:
            sys.modules.pop(n, None)
        comp_mod.begin_swap()
        app_mod._hot.reloading = True
        try:
            for name, path in jobs:
                with open(path, "rb") as f:
                    code = compile(f.read(), path, "exec")
                mod = types.ModuleType(name)
                mod.__file__ = path
                is_pkg = os.path.basename(path) == "__init__.py"
                mod.__package__ = name if is_pkg else name.rpartition(".")[0]
                if is_pkg:
                    mod.__path__ = [os.path.dirname(path)]
                sys.modules[name] = mod
                parent, _, child = name.rpartition(".")
                if parent and parent in sys.modules:
                    saved_attrs.append((sys.modules[parent], child, getattr(sys.modules[parent], child, None)))
                    setattr(sys.modules[parent], child, mod)
                exec(code, mod.__dict__)
            comp_mod.commit_swap()
            return None
        except BaseException as e:  # noqa: BLE001
            comp_mod.abort_swap()
            for k in [k for k in sys.modules if k not in saved_mods]:
                del sys.modules[k]
            sys.modules.update(saved_mods)
            for m, attr, old in saved_attrs:
                setattr(m, attr, old)
            return e
        finally:
            app_mod._hot.reloading = False
