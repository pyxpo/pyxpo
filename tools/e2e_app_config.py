"""Headless end-to-end check of the app config: compares the resolved [tool.pyxpo] values with what the built apps contain.

Usage (after `pyxpo build android` and/or `pyxpo build ios` in the project):
    .venv/bin/python tools/e2e_app_config.py test-apps/configdemo [--android APK] [--ios APP] [--release]

Android needs aapt2 from the Android SDK (ANDROID_HOME or ~/Library/Android/sdk). Exits 1 on any mismatch.
"""
import argparse
import glob
import io
import json
import os
import plistlib
import re
import subprocess
import sys
import zipfile
from pathlib import Path

from pyxpo.build import app_json
from pyxpo.config import load_config
from pyxpo.native_config import resolve

failures = []


def check(name, cond, detail=""):
    print("%s %s%s" % ("ok  " if cond else "FAIL", name, (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        failures.append(name)


def aapt2() -> str:
    sdk = os.environ.get("ANDROID_HOME") or os.path.expanduser("~/Library/Android/sdk")
    found = sorted(glob.glob(os.path.join(sdk, "build-tools", "*", "aapt2")))
    if not found:
        sys.exit("aapt2 not found under %s/build-tools" % sdk)
    return found[-1]


def check_android(nc, apk: Path) -> None:
    a = nc["android"]
    tool = aapt2()
    badging = subprocess.run([tool, "dump", "badging", str(apk)], capture_output=True, text=True, check=True).stdout
    tree = subprocess.run([tool, "dump", "xmltree", "--file", "AndroidManifest.xml", str(apk)],
                          capture_output=True, text=True, check=True).stdout
    pkg = re.search(r"package: name='([^']*)' versionCode='(\d+)' versionName='([^']*)'", badging)
    check("android package", pkg and pkg.group(1) == a["package"], pkg and pkg.group(1))
    check("android versionCode", pkg and int(pkg.group(2)) == a["version_code"], pkg and pkg.group(2))
    check("android versionName", pkg and pkg.group(3) == nc["version"], pkg and pkg.group(3))
    check("android minSdk", "minSdkVersion:'%d'" % a["min_sdk"] in badging)
    check("android targetSdk", "targetSdkVersion:'%d'" % a["target_sdk"] in badging)
    check("android label", "application-label:'%s'" % nc["name"] in badging)
    perms = set(re.findall(r"uses-permission: name='([^']*)'", badging))
    for p in a["permissions"]:
        check("android permission %s" % p, p in perms)
    for p in a["blocked_permissions"]:
        check("android blocked %s" % p, p not in perms)
    for s in nc["schemes"]:
        check("android scheme %s" % s, 'scheme(0x01010027)="%s"' % s in tree)
    check("android meta-data pyxpo.*", "pyxpo.user_interface_style" in tree)
    if a["icon"] or a["adaptive_icon"].get("foreground_image"):
        check("android launcher icon", "@mipmap/ic_launcher" in tree or "icon=" in badging)
    with zipfile.ZipFile(str(apk)) as z, zipfile.ZipFile(io.BytesIO(z.read("assets/pyxpo/app.zip"))) as app:
        shipped = json.loads(app.read("pyxpo/" + app_json.NAME))
    check("android Constants json", shipped == json.loads(app_json.dumps(nc)))


def check_ios(nc, app: Path) -> None:
    i = nc["ios"]
    with open(str(app / "Info.plist"), "rb") as f:
        pl = plistlib.load(f)
    check("ios bundle id", pl.get("CFBundleIdentifier") == i["bundle_id"], pl.get("CFBundleIdentifier"))
    check("ios version", pl.get("CFBundleShortVersionString") == nc["version"], pl.get("CFBundleShortVersionString"))
    check("ios build number", str(pl.get("CFBundleVersion")) == str(i["build_number"]), pl.get("CFBundleVersion"))
    check("ios display name", pl.get("CFBundleDisplayName", pl.get("CFBundleName")) == nc["name"])
    url_schemes = [s for t in pl.get("CFBundleURLTypes", []) for s in t.get("CFBundleURLSchemes", [])]
    for s in nc["schemes"]:
        check("ios scheme %s" % s, s in url_schemes)
    for k, v in i["info_plist"].items():
        check("ios Info.plist %s" % k, pl.get(k) == v, pl.get(k))
    if i["icon"].get("light"):
        check("ios app icon", (app / "Assets.car").is_file() and "CFBundleIcons" in pl)
    shipped = [p for p in app.rglob(app_json.NAME)]
    check("ios Constants json", len(shipped) == 1 and json.loads(shipped[0].read_text()) == json.loads(app_json.dumps(nc)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--android", help="APK path (default: the project's debug or release build)")
    ap.add_argument("--ios", help=".app path (default: the project's simulator build)")
    ap.add_argument("--release", action="store_true")
    args = ap.parse_args()
    project = Path(args.project).resolve()
    nc = resolve(load_config(project), project)
    kind = "release" if args.release else "debug"
    apk = Path(args.android) if args.android else project / "build/android/shell/app/build/outputs/apk" / kind / (
        "app-release-unsigned.apk" if args.release else "app-debug.apk")
    app = Path(args.ios) if args.ios else project / "build/ios/DerivedData/Build/Products" / (
        "%s-iphonesimulator" % kind.capitalize()) / ("%s.app" % nc["product_name"])
    ran = False
    if apk.is_file():
        check_android(nc, apk)
        ran = True
    if app.is_dir():
        check_ios(nc, app)
        ran = True
    if not ran:
        sys.exit("no build found: run `pyxpo build android` or `pyxpo build ios` first")
    print("%d failure(s)" % len(failures) if failures else "all checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
