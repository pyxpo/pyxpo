"""Ejecting native projects: user-owned files are written once, then only updated when the user has not edited them."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Tuple

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
