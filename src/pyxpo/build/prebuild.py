"""Ejecting native projects: user-owned files are written once, then only updated when the user has not edited them."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

STAMP = ".pyxpo-prebuild.json"
TEXT_SUFFIXES = (".yml", ".plist", ".swift", ".sh", ".h", ".m", ".kt", ".kts", ".xml", ".properties", ".gradle", ".txt")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def render(template: Path, values: Dict[str, str]) -> Dict[str, bytes]:
    """Template tree -> {relative path: bytes}, with `{{key}}` replaced in text files."""
    out: Dict[str, bytes] = {}
    for src in sorted(template.rglob("*")):
        if src.is_dir():
            continue
        data = src.read_bytes()
        if src.suffix in TEXT_SUFFIXES or src.name.startswith("."):
            text = data.decode()
            for k, v in values.items():
                text = text.replace("{{%s}}" % k, v)
            data = text.encode()
        out[str(src.relative_to(template)).replace("\\", "/")] = data
    return out


def read_stamp(dest: Path) -> Dict:
    try:
        return json.loads((dest / STAMP).read_text())
    except (OSError, ValueError):
        return {}


def is_ejected(dest: Path) -> bool:
    return (dest / STAMP).is_file()


def plan_prebuild(rendered: Dict[str, bytes], dest: Path, stamp: Dict) -> List[Tuple[str, str]]:
    """Per file: write (missing), overwrite (unedited since last prebuild), keep (identical), conflict (user edited)."""
    known = stamp.get("files", {})
    actions: List[Tuple[str, str]] = []
    for rel, data in rendered.items():
        path = dest / rel
        if not path.exists():
            actions.append(("write", rel))
            continue
        disk = sha(path.read_bytes())
        if disk == sha(data):
            actions.append(("keep", rel))
        elif known.get(rel) == disk:
            actions.append(("overwrite", rel))
        else:
            actions.append(("conflict", rel))
    return actions


def apply(rendered: Dict[str, bytes], dest: Path, version: str) -> List[Tuple[str, str]]:
    """Writes the plan; edited files are left alone and the new version lands beside them as `<file>.pyxpo-new`."""
    dest.mkdir(parents=True, exist_ok=True)
    actions = plan_prebuild(rendered, dest, read_stamp(dest))
    files = dict(read_stamp(dest).get("files", {}))
    for action, rel in actions:
        path = dest / rel
        if action in ("write", "overwrite"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(rendered[rel])
            files[rel] = sha(rendered[rel])
        elif action == "keep":
            files.setdefault(rel, sha(rendered[rel]))
        else:
            Path(str(path) + ".pyxpo-new").write_bytes(rendered[rel])
    (dest / STAMP).write_text(json.dumps({"pyxpo_version": version, "files": files}, indent=2, sort_keys=True) + "\n")
    return actions


def sync_tree(src: Path, dst: Path, keep: Iterable[str] = ()) -> None:
    """Makes `dst` match `src` but rewrites only changed files, so Gradle and Xcode keep their up-to-date checks and a
    build that is already reading `dst` never sees it missing. Top-level names in `keep` (filled later by staging)
    and every `build/` folder (Gradle output of the generated subprojects) are left alone. `src` is consumed."""
    keep = set(keep)
    dst.mkdir(parents=True, exist_ok=True)
    for root, dirs, files in os.walk(str(dst), topdown=True):
        rel = Path(root).relative_to(dst)
        dirs[:] = [d for d in dirs if d != "build" and not (rel == Path(".") and d in keep)]
        for name in list(dirs) + files:
            if rel == Path(".") and name in keep:
                continue
            d, s = Path(root) / name, src / rel / name
            if not os.path.lexists(str(s)) or s.is_symlink() != d.is_symlink() or s.is_dir() != d.is_dir():
                if d.is_dir() and not d.is_symlink():
                    shutil.rmtree(str(d))
                    dirs.remove(name)
                else:
                    d.unlink()
    for root, dirs, files in os.walk(str(src)):
        rel = Path(root).relative_to(src)
        (dst / rel).mkdir(exist_ok=True)
        for name in dirs + files:
            s, d = Path(root) / name, dst / rel / name
            if s.is_symlink():
                if not d.is_symlink() or os.readlink(str(d)) != os.readlink(str(s)):
                    if os.path.lexists(str(d)):
                        d.unlink()
                    os.symlink(os.readlink(str(s)), str(d))
                if name in dirs:
                    dirs.remove(name)
            elif s.is_file() and not (d.is_file() and d.stat().st_size == s.stat().st_size and d.read_bytes() == s.read_bytes()):
                shutil.copy2(str(s), str(d))
    shutil.rmtree(str(src))
