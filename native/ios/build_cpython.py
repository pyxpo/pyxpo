"""Cross-build CPython for iOS and assemble dist/ios/Python.xcframework.

Usage: python native/ios/build_cpython.py [--host arm64-apple-ios-simulator ...] [--version 3.13.7]
Default hosts: simulator arm64 only (fastest path). Add --all for device + x86_64 simulator.
Needs Xcode and a host CPython of the same version (built by the Android script, or --build-python).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".cache"
DIST = ROOT / "dist" / "ios"
sys.path.insert(0, str(ROOT / "native" / "android"))

# host triple -> (sdk, arch)
HOSTS: Dict[str, tuple] = {
    "arm64-apple-ios-simulator": ("iphonesimulator", "arm64"),
    "x86_64-apple-ios-simulator": ("iphonesimulator", "x86_64"),
    "arm64-apple-ios": ("iphoneos", "arm64"),
}
DEPS = [  # (release tag, asset prefix)
    ("BZip2-1.0.8-2", "bzip2-1.0.8-2"),
    ("XZ-5.6.4-2", "xz-5.6.4-2"),
    ("libFFI-3.4.7-2", "libffi-3.4.7-2"),
    ("OpenSSL-3.5.9-1", "openssl-3.5.9-1"),
]
DEPS_URL = "https://github.com/beeware/cpython-apple-source-deps/releases/download/%s/%s-%s.%s.tar.gz"


def fetch_deps(sdk: str, arch: str) -> Dict[str, Path]:
    out: Dict[str, Path] = {}
    for tag, prefix in DEPS:
        d = CACHE / "apple-deps" / ("%s.%s" % (sdk, arch)) / prefix.split("-")[0]
        if not d.is_dir():
            d.mkdir(parents=True)
            tgz = d.parent / ("%s.tar.gz" % prefix)
            urllib.request.urlretrieve(DEPS_URL % (tag, prefix, sdk, arch), tgz)
            with tarfile.open(tgz) as t:
                t.extractall(d)
            tgz.unlink()
        out[prefix.split("-")[0]] = d
    return out


def fetch_source(version: str) -> Path:
    src = CACHE / ("Python-%s" % version)
    if not src.is_dir():
        CACHE.mkdir(exist_ok=True)
        tgz = CACHE / ("Python-%s.tgz" % version)
        if not tgz.exists():
            urllib.request.urlretrieve("https://www.python.org/ftp/python/%s/Python-%s.tgz" % (version, version), tgz)
        with tarfile.open(tgz) as t:
            t.extractall(CACHE)
    return src


def build_python(src: Path) -> Path:
    """Host (macOS) Python of the same version, needed by the cross build."""
    exe = src / "cross-build" / "build" / "python.exe"
    if exe.is_file():
        return exe
    bdir = src / "cross-build" / "build"
    bdir.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(src / "configure"), "--quiet"], cwd=str(bdir), check=True)
    subprocess.run(["make", "-j%d" % (os.cpu_count() or 4)], cwd=str(bdir), check=True)
    return exe


def build(host: str, src: Path, build_py: Path) -> Path:
    sdk, arch = HOSTS[host]
    deps = fetch_deps(sdk, arch)
    bdir = src / "cross-build" / host
    install = bdir / "install"
    if (install / "Python.framework").is_dir():
        return install
    bdir.mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": ":".join([str(src / "iOS" / "Resources" / "bin"), "/usr/bin", "/bin", "/usr/sbin", "/sbin",
                          "/Library/Apple/usr/bin"]),
        "HOME": os.environ["HOME"],
        "LIBLZMA_CFLAGS": "-I%s/include" % deps["xz"],
        "LIBLZMA_LIBS": "-L%s/lib -llzma" % deps["xz"],
        "BZIP2_CFLAGS": "-I%s/include" % deps["bzip2"],
        "BZIP2_LIBS": "-L%s/lib -lbz2" % deps["bzip2"],
        "LIBFFI_CFLAGS": "-I%s/include" % deps["libffi"],
        "LIBFFI_LIBS": "-L%s/lib -lffi" % deps["libffi"],
    }
    if os.environ.get("DEVELOPER_DIR"):
        env["DEVELOPER_DIR"] = os.environ["DEVELOPER_DIR"]
    subprocess.run([
        str(src / "configure"), "--enable-framework=%s" % install, "--host=%s" % host,
        "--build=arm64-apple-darwin", "--with-build-python=%s" % build_py,
        "--with-openssl=%s" % deps["openssl"], "--quiet",
    ], cwd=str(bdir), env=env, check=True)
    jobs = "-j%d" % (os.cpu_count() or 4)
    subprocess.run(["make", jobs], cwd=str(bdir), env=env, check=True)
    subprocess.run(["make", "install"], cwd=str(bdir), env=env, check=True)
    return install


def _is_macho(p: Path) -> bool:
    if p.is_symlink() or not p.is_file():
        return False
    with open(str(p), "rb") as f:
        return f.read(4) in (b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca")


def merge_slices(installs: List[Path], out: Path) -> None:
    """Fat-merge thin installs of one SDK into out/. A single install is copied unchanged."""
    if out.exists():
        shutil.rmtree(str(out))
    shutil.copytree(str(installs[0]), str(out), symlinks=True)
    if len(installs) == 1:
        return
    for other in installs[1:]:
        for p in sorted(out.rglob("*")):
            if not _is_macho(p):
                continue
            q = other / p.relative_to(out)
            if q.is_file():
                tmp = p.with_suffix(p.suffix + ".fat")
                subprocess.run(["lipo", "-create", "-output", str(tmp), str(p), str(q)], check=True)
                tmp.replace(p)
        # union of stdlib files (platform-specific modules differ per arch)
        for q in other.rglob("*"):
            r = out / q.relative_to(other)
            if q.is_file() and not r.exists():
                r.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(q), str(r))


def fix_headers(framework: Path, src: Path, archs: List[str], thin: List[Path]) -> None:
    """Multi-arch pyconfig.h shim (CPython README, 'Merge thin frameworks')."""
    hdr = framework / "Headers"
    if len(archs) == 1:
        return
    shutil.copy2(str(hdr / "pyconfig.h"), str(hdr / ("pyconfig-%s.h" % archs[0])))
    for arch, t in zip(archs[1:], thin[1:]):
        shutil.copy2(str(t / "Python.framework" / "Headers" / "pyconfig.h"), str(hdr / ("pyconfig-%s.h" % arch)))
    shutil.copy2(str(src / "iOS" / "Resources" / "pyconfig.h"), str(hdr / "pyconfig.h"))


def assemble(built: Dict[str, Path], src: Path, version: str) -> None:
    work = DIST / "_work"
    if work.exists():
        shutil.rmtree(str(work))
    groups: Dict[str, List[str]] = {}
    for host in built:
        groups.setdefault(HOSTS[host][0], []).append(host)
    frameworks: List[Path] = []
    slices: Dict[str, Path] = {}
    for sdk, hosts in groups.items():
        out = work / sdk
        merge_slices([built[h] for h in hosts], out)
        fix_headers(out / "Python.framework", src, [HOSTS[h][1] for h in hosts], [built[h] for h in hosts])
        frameworks.append(out / "Python.framework")
        slices[sdk] = out
    xc = DIST / "Python.xcframework"
    if xc.exists():
        shutil.rmtree(str(xc))
    cmd = ["xcodebuild", "-create-xcframework", "-output", str(xc)]
    for fw in frameworks:
        cmd += ["-framework", str(fw)]
    subprocess.run(cmd, check=True)
    # copy lib/ and bin/ into the matching slice dir of the xcframework
    info = json.loads(subprocess.run(["plutil", "-convert", "json", "-o", "-", str(xc / "Info.plist")],
                                     check=True, capture_output=True, text=True).stdout)
    for lib in info["AvailableLibraries"]:
        sdk = "iphonesimulator" if lib.get("LibraryIdentifier", "").endswith("simulator") else "iphoneos"
        for sub in ("lib", "bin"):
            d = slices[sdk] / sub
            if d.is_dir():
                shutil.copytree(str(d), str(xc / lib["LibraryIdentifier"] / sub), symlinks=True)
    shutil.rmtree(str(work))
    h = hashlib.sha256()
    files = {}
    for p in sorted(xc.rglob("*")):
        if p.is_file() and not p.is_symlink():
            files[str(p.relative_to(xc))] = hashlib.sha256(p.read_bytes()).hexdigest()
            h.update(files[str(p.relative_to(xc))].encode())
    (DIST / "manifest.json").write_text(json.dumps(
        {"python": version, "hosts": sorted(built), "digest": h.hexdigest()[:16]}, indent=1))
    print("built %s -> %s (%d files)" % (", ".join(sorted(built)), xc, len(files)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", action="append", choices=sorted(HOSTS))
    ap.add_argument("--all", action="store_true", help="device + both simulator archs")
    ap.add_argument("--version", default="3.13.7")
    ap.add_argument("--build-python", help="host python.exe of the same version")
    args = ap.parse_args()
    hosts = sorted(HOSTS) if args.all else (args.host or ["arm64-apple-ios-simulator"])
    src = fetch_source(args.version)
    build_py = Path(args.build_python) if args.build_python else build_python(src)
    DIST.mkdir(parents=True, exist_ok=True)
    built = {h: build(h, src, build_py) for h in hosts}
    assemble(built, src, args.version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
