"""Wrap native extension modules (*.so) as iOS frameworks inside an app bundle.

App Store rules forbid loose dylibs, so CPython's iOS port loads each extension from
Frameworks/<dotted.module>.framework/<dotted.module>, found through a `.fwork` placeholder
left where the .so was. This script runs inside the Xcode build phase, before the bundle
is signed, with the system python3 (3.9): standard library only.
"""
from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import subprocess
import sys
from typing import Iterable, List, Tuple

# (directory relative to the bundle, module-name base relative to the bundle)
ROOTS = [
    ("python/lib/python3.13/lib-dynload", "python/lib/python3.13/lib-dynload"),
    ("app_packages", "app_packages"),
    ("app_root", "app_root"),
]


def module_name(rel_to_base: str) -> str:
    """'numpy/core/_x.cpython-313-iphoneos.so' -> 'numpy.core._x'"""
    parts = rel_to_base.replace(os.sep, "/").split("/")
    parts[-1] = parts[-1].split(".")[0]
    return ".".join(parts)


def find_extensions(bundle: str) -> List[Tuple[str, str, str]]:
    """Return (path, base_rel, module) for every .so under the known roots."""
    out = []
    for root_rel, base_rel in ROOTS:
        root = os.path.join(bundle, root_rel)
        for dp, _dns, fns in os.walk(root):
            for fn in sorted(fns):
                if not fn.endswith(".so"):
                    continue
                full = os.path.join(dp, fn)
                out.append((full, base_rel, module_name(os.path.relpath(full, root))))
    return out


def wrap(bundle: str, template: str, bundle_id: str, platform: str = "iPhoneOS", min_os: str = "15.0") -> List[str]:
    """Move each .so into its own framework. Returns the framework dirs created."""
    with open(template, "rb") as f:
        info_tpl = plistlib.load(f)
    frameworks: List[str] = []
    for path, base_rel, mod in find_extensions(bundle):
        fw_rel = "Frameworks/%s.framework" % mod
        fw = os.path.join(bundle, fw_rel)
        if not os.path.isdir(fw):
            os.makedirs(fw)
            info = dict(info_tpl)
            info["CFBundleExecutable"] = mod
            info["CFBundleIdentifier"] = ("%s.%s" % (bundle_id, mod)).replace("_", "-")
            info["CFBundleSupportedPlatforms"] = [platform]
            info["MinimumOSVersion"] = min_os
            with open(os.path.join(fw, "Info.plist"), "wb") as f:
                plistlib.dump(info, f)
            frameworks.append(fw)
        shutil.move(path, os.path.join(fw, mod))
        stem = os.path.relpath(path[:-3], bundle).replace(os.sep, "/")
        with open(path[:-3] + ".fwork", "w") as f:
            f.write("%s/%s" % (fw_rel, mod))
        with open(os.path.join(fw, mod + ".origin"), "w") as f:
            f.write(stem + ".fwork")
    return frameworks


def prune(bundle: str) -> List[str]:
    """Removes extension frameworks whose module left the bundle. An incremental Xcode build keeps the Frameworks
    of an earlier build, so a dropped package or stdlib module would ship on. Only frameworks this script made
    (they carry a .origin file) are touched."""
    gone = []
    fw_dir = os.path.join(bundle, "Frameworks")
    for name in sorted(os.listdir(fw_dir)) if os.path.isdir(fw_dir) else []:
        fw = os.path.join(fw_dir, name)
        origin = os.path.join(fw, name[:-len(".framework")] + ".origin")
        if not (name.endswith(".framework") and os.path.isfile(origin)):
            continue
        with open(origin) as f:
            if os.path.isfile(os.path.join(bundle, f.read().strip())):
                continue
        shutil.rmtree(fw)
        gone.append(fw)
    return gone


def sign(frameworks: Iterable[str], identity: str) -> None:
    for fw in frameworks:
        subprocess.run(["/usr/bin/codesign", "--force", "--sign", identity, "--timestamp=none",
                        "--preserve-metadata=identifier,entitlements,flags", fw], check=True)


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--template", required=True)
    ap.add_argument("--bundle-id", required=True)
    ap.add_argument("--sdk", default="iphoneos")
    ap.add_argument("--sign", default="-")
    ns = ap.parse_args(argv)
    platform = "iPhoneSimulator" if "simulator" in ns.sdk else "iPhoneOS"
    fws = wrap(ns.bundle, ns.template, ns.bundle_id, platform)
    gone = prune(ns.bundle)
    # Also sign pre-existing frameworks (e.g. wheels shipped as frameworks); idempotent.
    sign(fws, ns.sign)
    print("pyxpo: wrapped %d extension frameworks, removed %d stale" % (len(fws), len(gone)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
