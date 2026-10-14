from __future__ import annotations

import hashlib
import io
import json
import os
import tarfile
from pathlib import Path

import pytest

from pyxpo.build import runtime
from pyxpo.build.runtime import BuildError


def make_tar(path: Path, members) -> None:
    with tarfile.open(str(path), "w:gz") as t:
        for name, kind, payload in members:
            ti = tarfile.TarInfo(name)
            if kind == "file":
                ti.size = len(payload)
                t.addfile(ti, io.BytesIO(payload))
            elif kind == "sym":
                ti.type = tarfile.SYMTYPE
                ti.linkname = payload
                t.addfile(ti)
            elif kind == "hard":
                ti.type = tarfile.LNKTYPE
                ti.linkname = payload
                t.addfile(ti)
            elif kind == "fifo":
                ti.type = tarfile.FIFOTYPE
                t.addfile(ti)


def asset_for(path: Path, d="ios"):
    data = path.read_bytes()
    return {"file": path.name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "dir": d}


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("PYXPO_CACHE_DIR", str(tmp_path / "cache"))
    for v in ("PYXPO_IOS_DIST", "PYXPO_ANDROID_DIST", "PYXPO_RUNTIME_ARCHIVES", "PYXPO_RUNTIME_BASE_URL", "PYXPO_OFFLINE"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(runtime, "is_dev_checkout", lambda: False)
    return tmp_path / "cache"


def manifest_with(tmp_path, monkeypatch, assets, base="https://example.invalid/rel/"):
    m = {"runtime": "9.9.9-1", "python": "9.9.9", "base_url": base, "assets": assets}
    monkeypatch.setattr(runtime, "load_manifest", lambda: m)
    return m


def test_dist_path_order(tmp_path, monkeypatch, cache):
    manifest_with(tmp_path, monkeypatch, {})
    assert runtime.dist_path("ios") == cache / "runtime" / "9.9.9-1" / "ios"
    monkeypatch.setattr(runtime, "is_dev_checkout", lambda: True)
    assert runtime.dist_path("ios") == runtime.REPO / "dist" / "ios"
    monkeypatch.setenv("PYXPO_IOS_DIST", str(tmp_path / "mine"))
    assert runtime.dist_path("ios") == tmp_path / "mine"
    assert runtime.source("ios") == "override"


def test_installed_layout_is_not_dev_checkout():
    # the real check: this repo is a checkout, a site-packages copy is not
    assert runtime.is_dev_checkout() == ((runtime.REPO / "pyproject.toml").is_file() and (runtime.REPO / "src" / "pyxpo").is_dir())


def test_ensure_skips_paths_outside_cache(tmp_path, monkeypatch, cache):
    manifest_with(tmp_path, monkeypatch, {"ios": {"file": "x", "sha256": "0", "size": 1, "dir": "ios"}})
    assert runtime.ensure("ios", path=tmp_path / "elsewhere") == tmp_path / "elsewhere"
    assert not (cache / "runtime").exists()


def test_fetch_from_archives_dir_and_stamp(tmp_path, monkeypatch, cache):
    tar = tmp_path / "arch" / "ios.tar.gz"
    tar.parent.mkdir()
    make_tar(tar, [("Python.xcframework/a.txt", "file", b"hi"), ("lnk", "sym", "Python.xcframework/a.txt")])
    manifest_with(tmp_path, monkeypatch, {"ios": asset_for(tar)})
    monkeypatch.setenv("PYXPO_RUNTIME_ARCHIVES", str(tar.parent))
    dest = runtime.ensure("ios")
    assert (dest / "Python.xcframework" / "a.txt").read_bytes() == b"hi"
    assert (dest / "lnk").is_symlink()
    assert json.loads((dest / runtime.STAMP).read_text())["file"] == "ios.tar.gz"
    assert runtime.status()["platforms"]["ios"]["items"] == {"ios": "cached"}


def test_hash_mismatch_leaves_nothing(tmp_path, monkeypatch, cache):
    tar = tmp_path / "arch" / "ios.tar.gz"
    tar.parent.mkdir()
    make_tar(tar, [("a", "file", b"x")])
    asset = asset_for(tar)
    asset["sha256"] = "0" * 64
    manifest_with(tmp_path, monkeypatch, {"ios": asset})
    monkeypatch.setenv("PYXPO_RUNTIME_ARCHIVES", str(tar.parent))
    with pytest.raises(BuildError, match="sha256 mismatch"):
        runtime.ensure("ios")
    assert not (cache / "runtime" / "9.9.9-1" / "ios").exists()


def test_download_rejects_http_and_http_redirect_and_oversize(tmp_path):
    dest = tmp_path / "f"
    with pytest.raises(BuildError, match="non-https"):
        runtime.download("http://example.com/x", dest, "0", 1)

    class Resp(io.BytesIO):
        def __init__(self, data, final):
            super().__init__(data)
            self._final = final

        def geturl(self):
            return self._final

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with pytest.raises(BuildError, match="non-https"):
        runtime.download("https://a/x", dest, "0", 10, opener=lambda u, timeout: Resp(b"abc", "http://evil/x"))
    with pytest.raises(BuildError, match="larger than"):
        runtime.download("https://a/x", dest, "0", 2, opener=lambda u, timeout: Resp(b"abcdef", "https://a/x"))
    data = b"abc"
    runtime.download("https://a/x", dest, hashlib.sha256(data).hexdigest(), 3, opener=lambda u, timeout: Resp(data, "https://a/x"))
    assert dest.read_bytes() == data


@pytest.mark.parametrize("members", [
    [("../x", "file", b"")],
    [("/abs", "file", b"")],
    [("l", "sym", "/etc/passwd")],
    [("l", "sym", "../../etc")],
    [("l", "hard", "../x")],
    [("p", "fifo", None)],
    # lexically inside, but resolves through another symlink to outside (no extraction filter on old 3.9)
    [("a/b/s", "sym", "../.."), ("t", "sym", "a/b/s/../.."), ("t/x", "file", b"")],
    [("d", "sym", "."), ("e", "sym", "d/d/.."), ("e/x", "file", b"")],
    # writing through a symlink, also case-insensitively (APFS)
    [("a", "file", b""), ("l", "sym", "a"), ("l/x", "file", b"")],
    [("Lib", "sym", "."), ("lib/x", "file", b"")],
    # duplicate name (would overwrite through an earlier link), hardlink via symlink or to a symlink
    [("a", "file", b""), ("h", "hard", "a"), ("h", "file", b"")],
    [("s", "sym", "."), ("f", "file", b""), ("h", "hard", "s/f")],
    [("f", "file", b""), ("s", "sym", "f"), ("h", "hard", "s")],
])
def test_unsafe_archives_rejected(tmp_path, members):
    tar = tmp_path / "t.tar.gz"
    make_tar(tar, members)
    with tarfile.open(str(tar)) as t, pytest.raises(BuildError):
        runtime.safe_members(t, tmp_path / "dest")


def test_internal_symlink_ok(tmp_path):
    tar = tmp_path / "t.tar.gz"
    make_tar(tar, [("a/b", "file", b"1"), ("a/l", "sym", "b"), ("c/l2", "sym", "../a/b")])
    with tarfile.open(str(tar)) as t:
        assert len(runtime.safe_members(t, tmp_path / "dest")) == 3


def test_parallel_build_finished_first(tmp_path, monkeypatch, cache):
    tar = tmp_path / "ios.tar.gz"
    make_tar(tar, [("a", "file", b"x")])
    asset = asset_for(tar)
    dest = cache / "runtime" / "9.9.9-1" / "ios"
    dest.mkdir(parents=True)
    (dest / runtime.STAMP).write_text(__import__("json").dumps({"sha256": asset["sha256"]}))
    (dest / "mark").write_text("theirs")
    runtime._extract_atomic(tar, asset, dest)
    assert (dest / "mark").read_text() == "theirs"
    assert not [p for p in dest.parent.iterdir() if p.name.startswith(".tmp-")]


def test_offline_without_cache_names_the_fix(tmp_path, monkeypatch, cache):
    manifest_with(tmp_path, monkeypatch, {"ios": {"file": "ios.tar.gz", "sha256": "0", "size": 1, "dir": "ios"}})
    monkeypatch.setenv("PYXPO_OFFLINE", "1")
    with pytest.raises(BuildError, match="PYXPO_RUNTIME_ARCHIVES"):
        runtime.ensure("ios")


def test_android_only_requested_abis(tmp_path, monkeypatch, cache):
    arch = tmp_path / "arch"
    arch.mkdir()
    assets = {}
    for abi in ("arm64-v8a", "x86_64"):
        t = arch / ("a-%s.tar.gz" % abi)
        make_tar(t, [("prefix/x", "file", b"1")])
        assets["android-" + abi] = asset_for(t, "android/" + abi)
    manifest_with(tmp_path, monkeypatch, assets)
    monkeypatch.setenv("PYXPO_RUNTIME_ARCHIVES", str(arch))
    runtime.ensure("android", ["x86_64"])
    root = cache / "runtime" / "9.9.9-1" / "android"
    assert (root / "x86_64" / "prefix" / "x").is_file() and not (root / "arm64-v8a").exists()


def test_clean(tmp_path, monkeypatch, cache):
    manifest_with(tmp_path, monkeypatch, {})
    (cache / "runtime" / "9.9.9-1").mkdir(parents=True)
    (cache / "runtime" / "old").mkdir()
    assert [p.name for p in runtime.clean()] == ["9.9.9-1"]
    assert [p.name for p in runtime.clean(all_versions=True)] == ["old"]


def test_shipped_manifest_is_valid():
    m = json.loads(runtime.MANIFEST.read_text())
    assert m["base_url"].startswith("https://") and m["assets"]
    for a in m["assets"].values():
        assert len(a["sha256"]) == 64 and a["size"] > 0 and a["file"].endswith(".tar.gz")
