"""Prebuilt CPython runtimes: locate them, or download them once into the user cache.

A pip-installed pyxpo ships no CPython binaries (they are too big for PyPI). `runtime_manifest.json` pins the
release assets by sha256; `ensure()` fetches what a build needs into `<cache>/runtime/<version>/<dir>`.
A source checkout uses `<repo>/dist/<platform>` and never downloads.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import sys
import tarfile
import tempfile
import unicodedata
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

MANIFEST = Path(__file__).resolve().parent / "runtime_manifest.json"
REPO = Path(__file__).resolve().parents[3]
STAMP = ".pyxpo-runtime.json"
ENV_DIST = {"ios": "PYXPO_IOS_DIST", "android": "PYXPO_ANDROID_DIST"}


class BuildError(Exception):
    """Any build or runtime-fetch problem; the CLI prints it without a traceback."""


def load_manifest() -> Dict[str, Any]:
    return json.loads(MANIFEST.read_text())


def is_dev_checkout() -> bool:
    return (REPO / "pyproject.toml").is_file() and (REPO / "src" / "pyxpo").is_dir()


def cache_root() -> Path:
    if os.environ.get("PYXPO_CACHE_DIR"):
        return Path(os.environ["PYXPO_CACHE_DIR"]).expanduser()
    if os.environ.get("XDG_CACHE_HOME"):
        return Path(os.environ["XDG_CACHE_HOME"]) / "pyxpo"
    return Path.home() / ".cache" / "pyxpo"


def runtime_root(manifest: Optional[Dict[str, Any]] = None) -> Path:
    return cache_root() / "runtime" / (manifest or load_manifest())["runtime"]


def source(platform: str) -> str:
    """Where `dist_path` comes from: override, dev, or cache."""
    if os.environ.get(ENV_DIST[platform]):
        return "override"
    return "dev" if is_dev_checkout() else "cache"


def dist_path(platform: str) -> Path:
    """Directory holding the CPython build for `platform` ("ios" or "android"). Never touches the network."""
    if os.environ.get(ENV_DIST[platform]):
        return Path(os.environ[ENV_DIST[platform]])
    if is_dev_checkout():
        return REPO / "dist" / platform
    return runtime_root() / platform


def native_common() -> Path:
    if os.environ.get("PYXPO_NATIVE_COMMON"):
        return Path(os.environ["PYXPO_NATIVE_COMMON"])
    return Path(__file__).resolve().parent.parent / "_native" / "common"


def assets_for(platform: str, manifest: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {k: v for k, v in manifest["assets"].items() if v["dir"].split("/")[0] == platform}


def _under(path: Path, root: Path) -> bool:
    try:
        Path(os.path.realpath(path)).relative_to(os.path.realpath(root))
        return True
    except ValueError:
        return False


def is_complete(dest: Path, asset: Optional[Dict[str, Any]] = None) -> bool:
    """Stamp present (and, when `asset` is given, written for the same sha256 as the manifest pins)."""
    stamp = dest / STAMP
    if not stamp.is_file():
        return False
    if asset is None:
        return True
    try:
        return json.loads(stamp.read_text()).get("sha256") == asset["sha256"]
    except (OSError, ValueError):
        return False


def ensure(platform: str, abis: Optional[Iterable[str]] = None, path: Optional[Path] = None) -> Path:
    """Make the runtime for `platform` available (downloading assets when `path` is in the pyxpo cache)."""
    path = Path(path) if path is not None else dist_path(platform)
    if not _under(path, cache_root()):
        return path  # override or dev checkout: use as is
    manifest = load_manifest()
    wanted = list(abis) if abis is not None else None
    for name, asset in assets_for(platform, manifest).items():
        if wanted is not None and platform == "android" and asset["dir"].split("/", 1)[1] not in wanted:
            continue
        dest = runtime_root(manifest) / asset["dir"]
        if not is_complete(dest, asset):
            fetch_asset(manifest, name, dest)
    return path


def fetch_asset(manifest: Dict[str, Any], name: str, dest: Path) -> None:
    asset = manifest["assets"][name]
    archives = os.environ.get("PYXPO_RUNTIME_ARCHIVES")
    if archives:
        archive = Path(archives) / asset["file"]
        if not archive.is_file():
            raise BuildError("%s not found in PYXPO_RUNTIME_ARCHIVES=%s" % (asset["file"], archives))
        # copied (and hashed while copying) into the cache, so the bytes extracted are the bytes verified
        url = archive.resolve().as_uri()
    elif os.environ.get("PYXPO_OFFLINE"):
        raise BuildError("runtime %s is not in the cache (%s) and PYXPO_OFFLINE is set; run `pyxpo runtime fetch` "
                            "online, or set PYXPO_RUNTIME_ARCHIVES=<dir with %s>" % (name, dest, asset["file"]))
    else:
        base = os.environ.get("PYXPO_RUNTIME_BASE_URL") or manifest["base_url"]
        if not base.endswith("/"):
            base += "/"
        url = base + asset["file"]
    parent = dest.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".dl-", dir=str(parent))
    os.close(fd)
    try:
        if not archives:
            print("downloading %s (%.0f MB) ..." % (asset["file"], asset["size"] / 1e6), file=sys.stderr)
        download(url, Path(tmp), asset["sha256"], asset["size"])
        _extract_atomic(Path(tmp), asset, dest)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _check_url(url: str) -> None:
    if not (url.startswith("https://") or url.startswith("file://")):
        raise BuildError("refusing non-https runtime URL %s (set PYXPO_RUNTIME_BASE_URL to an https:// or file:// URL)" % url)


def download(url: str, dest: Path, sha256: str, size: int, opener: Any = None) -> None:
    """Stream `url` to `dest`, enforcing https, the pinned size, and the pinned sha256."""
    _check_url(url)
    open_url = opener or urllib.request.urlopen
    h = hashlib.sha256()
    total = 0
    try:
        with open_url(url, timeout=60) as resp:
            final = resp.geturl() if hasattr(resp, "geturl") else url
            _check_url(final)
            with open(str(dest), "wb") as out:
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > size:
                        raise BuildError("%s is larger than the %d bytes pinned in the manifest" % (url, size))
                    h.update(chunk)
                    out.write(chunk)
    except BuildError:
        raise
    except OSError as e:  # URLError, HTTPError, timeouts, disk full
        raise BuildError("download of %s failed: %s. Check your network, or set PYXPO_RUNTIME_ARCHIVES=<dir> "
                            "with the file, or PYXPO_RUNTIME_BASE_URL to a mirror" % (url, e))
    if h.hexdigest() != sha256 or total != size:
        raise BuildError("sha256 mismatch for %s (got %s, expected %s); file discarded" % (url, h.hexdigest(), sha256))


def _key(parts: Iterable[str]) -> str:
    # macOS file systems are case- and normalization-insensitive: compare paths the way the disk will
    return unicodedata.normalize("NFD", "/".join(parts)).casefold()


def _resolve_link(start: List[str], linkname: str, symlinks: set, what: str) -> List[str]:
    """Lexically resolve `linkname` from directory `start`; it must stay inside and never pass through a symlink."""
    if not linkname or os.path.isabs(linkname) or "\\" in linkname:
        raise BuildError("%s escapes the archive: %r" % (what, linkname))
    stack = list(start)
    comps = [c for c in linkname.split("/") if c not in ("", ".")]
    for i, c in enumerate(comps):
        if c == "..":
            if not stack:
                raise BuildError("%s escapes the archive: %r" % (what, linkname))
            stack.pop()
            continue
        stack.append(c)
        if i < len(comps) - 1 and _key(stack) in symlinks:
            raise BuildError("%s goes through another symlink: %r" % (what, linkname))
    return stack


def safe_members(tar: tarfile.TarFile, dest: Path) -> List[tarfile.TarInfo]:
    """Return members that are safe to extract under `dest`; raise on anything that could escape or is special.

    This must hold on its own (Python 3.9 before 3.9.17 has no extraction filters): no member may be written
    through a symlink, no link may resolve through another symlink or outside, and names must be unique, so
    neither the archive's order nor a later member can redirect a write.
    """
    members = tar.getmembers()
    symlinks = {_key(Path(m.name).parts) for m in members if m.issym()}
    seen: set = set()
    files: set = set()
    out = []
    for m in members:
        name = m.name
        if os.path.isabs(name) or ".." in Path(name).parts or "\\" in name:
            raise BuildError("unsafe path in runtime archive: %r" % name)
        if m.isdev() or m.isfifo():
            raise BuildError("special file in runtime archive: %r" % name)
        if not (m.isfile() or m.isdir() or m.issym() or m.islnk()):
            raise BuildError("unsupported entry in runtime archive: %r" % name)
        parts = list(Path(name).parts)
        key = _key(parts)
        if parts and key in seen:
            raise BuildError("duplicate entry in runtime archive: %r" % name)
        seen.add(key)
        if any(_key(parts[:i]) in symlinks for i in range(1, len(parts))):
            raise BuildError("entry is written through a symlink: %r" % name)
        if m.issym():
            _resolve_link(parts[:-1], m.linkname, symlinks, "symlink %r" % name)
        if m.islnk():
            target = _resolve_link([], m.linkname, symlinks, "hardlink %r" % name)
            if _key(target) not in files:  # only to a regular file extracted earlier
                raise BuildError("hardlink to a non-file or later entry: %r -> %r" % (name, m.linkname))
        if m.isfile():
            files.add(key)
        m.mode &= ~(stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX)
        m.mode |= stat.S_IRUSR | stat.S_IWUSR | (stat.S_IXUSR if m.isdir() else 0)
        out.append(m)
    return out


def _extract_atomic(archive: Path, asset: Dict[str, Any], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".tmp-", dir=str(dest.parent)))
    try:
        with tarfile.open(str(archive), "r:*") as tar:
            members = safe_members(tar, tmp)
            try:
                tar.extractall(str(tmp), members=members, filter="data")  # type: ignore[call-arg]
            except TypeError:  # Python without extraction filters: safe_members already vetted everything
                tar.extractall(str(tmp), members=members)
        (tmp / STAMP).write_text(json.dumps({"file": asset["file"], "sha256": asset["sha256"]}))
        try:
            os.rename(str(tmp), str(dest))
        except OSError:
            if is_complete(dest, asset):  # a parallel build finished first
                return
            if dest.exists():
                shutil.rmtree(str(dest))
            os.rename(str(tmp), str(dest))
    except (tarfile.TarError, EOFError) as e:
        raise BuildError("cannot read runtime archive %s: %s" % (archive.name, e))
    finally:
        if tmp.exists():
            shutil.rmtree(str(tmp), ignore_errors=True)


def clean(all_versions: bool = False) -> List[Path]:
    """Delete cached runtimes (the current one, or all). Returns removed paths."""
    root = cache_root() / "runtime"
    removed = []
    if not root.is_dir():
        return removed
    keep = None if all_versions else runtime_root()
    for p in sorted(root.iterdir()):
        if keep is None or p == keep:
            shutil.rmtree(str(p), ignore_errors=True)
            removed.append(p)
    return removed


def status() -> Dict[str, Any]:
    """For `pyxpo doctor`: runtime version and per-asset state. Never downloads."""
    m = load_manifest()
    out: Dict[str, Any] = {"runtime": m["runtime"], "cache": str(cache_root()), "platforms": {}}
    for plat in ("ios", "android"):
        src = source(plat)
        if src == "cache":
            items = {n: ("cached" if is_complete(runtime_root(m) / a["dir"], a) else "missing")
                     for n, a in assets_for(plat, m).items()}
        else:
            items = {plat: str(dist_path(plat))}
        out["platforms"][plat] = {"source": src, "items": items}
    return out
