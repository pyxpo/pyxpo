"""Build a pyxpo-wheels recipe for Android with cibuildwheel (needs Python >= 3.11, cibuildwheel >= 3.1).

Usage: python wheels/build.py numpy [--arch arm64_v8a ...] [--out wheels/dist]
Downloads the sdist from PyPI, builds cp313 wheels, then runs check_wheel.py on each result.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tomllib
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CACHE = ROOT / ".cache" / "src"


def fetch_sdist(name: str, version: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen("https://pypi.org/pypi/%s/%s/json" % (name, version)) as r:
        info = json.load(r)
    sd = next(u for u in info["urls"] if u["packagetype"] == "sdist")
    dest = CACHE / sd["filename"]
    if not dest.exists():
        urllib.request.urlretrieve(sd["url"], dest)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("recipe")
    ap.add_argument("--arch", action="append")
    ap.add_argument("--out", default=str(ROOT / "wheels" / "dist"))
    args = ap.parse_args()
    rec = tomllib.loads((HERE / "recipes" / (args.recipe + ".toml")).read_text())
    pkg, bld = rec["package"], rec.get("build", {})
    sdist = fetch_sdist(pkg["name"], pkg["version"])
    settings = list(bld.get("config_settings", [])) + ["setup-args=--cross-file=%s" % (HERE / "meson-android.ini")]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    before = set(out.glob("*.whl"))
    for arch in args.arch or bld.get("android_archs", ["arm64_v8a"]):
        env = dict(os.environ, CIBW_BUILD="cp313-*", CIBW_ARCHS_ANDROID=arch, CIBW_TEST_COMMAND="",
                   CIBW_BEFORE_BUILD="", CIBW_CONFIG_SETTINGS_ANDROID=" ".join(settings))
        env.setdefault("ANDROID_HOME", str(Path.home() / "Library" / "Android" / "sdk"))
        subprocess.run(["cibuildwheel", "--platform", "android", "--output-dir", str(out), str(sdist)],
                       env=env, check=True)
    new = sorted(set(out.glob("*.whl")) - before) or sorted(out.glob("*.whl"))
    rc = subprocess.run([sys.executable, str(HERE / "check_wheel.py")] + [str(w) for w in new]).returncode
    return rc


if __name__ == "__main__":
    sys.exit(main())
