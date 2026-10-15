"""iOS native settings derived from the app config: Info.plist, entitlements, xcconfig keys."""
from __future__ import annotations

import copy
import plistlib
from pathlib import Path
from typing import Any, Dict

PORTRAIT = "UIInterfaceOrientationPortrait"
LANDSCAPE = ["UIInterfaceOrientationLandscapeLeft", "UIInterfaceOrientationLandscapeRight"]
ALL_ORIENTATIONS = [PORTRAIT, "UIInterfaceOrientationPortraitUpsideDown"] + LANDSCAPE
STYLES = {"light": "Light", "dark": "Dark"}


def deep_merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_merge(base[k], v)
        else:
            base[k] = copy.deepcopy(v)
    return base


def info_plist(base: Dict[str, Any], nc: Dict[str, Any]) -> Dict[str, Any]:
    """The user's App/Info.plist with the app config applied on top. Raw `ios.info_plist` wins, as in Expo."""
    ios = nc["ios"]
    p = copy.deepcopy(base)
    urls = [u for u in p.get("CFBundleURLTypes", []) if u.get("CFBundleURLSchemes") != ["$(PYXPO_SCHEME)"]]
    p["CFBundleURLTypes"] = [{"CFBundleURLSchemes": list(nc["schemes"])}] + urls
    orient = ios["orientation"]
    if orient == "portrait":
        p["UISupportedInterfaceOrientations"] = [PORTRAIT]
    elif orient == "landscape":
        p["UISupportedInterfaceOrientations"] = list(LANDSCAPE)
    if orient != "default" or ios["require_full_screen"] or "UISupportedInterfaceOrientations~ipad" in p:
        if ios["supports_tablet"]:
            p["UISupportedInterfaceOrientations~ipad"] = list(ALL_ORIENTATIONS) if not ios["require_full_screen"] \
                else list(p.get("UISupportedInterfaceOrientations") or ALL_ORIENTATIONS)
    style = ios["user_interface_style"]
    if style in STYLES:
        p["UIUserInterfaceStyle"] = STYLES[style]
    else:
        p.pop("UIUserInterfaceStyle", None)
    if ios["require_full_screen"]:
        p["UIRequiresFullScreen"] = True
    if ios["uses_non_exempt_encryption"] is not None:
        p["ITSAppUsesNonExemptEncryption"] = bool(ios["uses_non_exempt_encryption"])
    launch = {"UIColorName": "SplashBackground"}
    if ios["splash"].get("image"):
        launch["UIImageName"] = "SplashImage"
    p["UILaunchScreen"] = launch
    p.pop("UILaunchStoryboardName", None)
    p["PyxpoBackgroundColor"] = ios["background_color"]
    p["PyxpoStatusBarStyle"] = nc["status_bar"]["style"]
    p["PyxpoStatusBarHidden"] = nc["status_bar"]["hidden"]
    p["PyxpoUserInterfaceStyle"] = style
    deep_merge(p, ios["info_plist"])
    return p


def entitlements(nc: Dict[str, Any]) -> Dict[str, Any]:
    ios = nc["ios"]
    e: Dict[str, Any] = {}
    if ios["associated_domains"]:
        e["com.apple.developer.associated-domains"] = list(ios["associated_domains"])
    if ios["uses_apple_sign_in"]:
        e["com.apple.developer.applesignin"] = ["Default"]
    return deep_merge(e, ios["entitlements"])


def xcconfig_lines(nc: Dict[str, Any], has_entitlements: bool, extra: Dict[str, str] = None) -> list:
    ios = nc["ios"]
    lines = [
        "PYXPO_INFOPLIST = pyxpo-gen/Info.plist",
        "PYXPO_DEVICE_FAMILY = %s" % ("1,2" if ios["supports_tablet"] else "1"),
        "IPHONEOS_DEPLOYMENT_TARGET = %s" % ios["deployment_target"],
    ]
    if has_entitlements:
        lines.append("CODE_SIGN_ENTITLEMENTS = pyxpo-gen/App.entitlements")
    lines += ["%s = %s" % (k, v) for k, v in (extra or {}).items()]  # last, so config plugin settings win
    return lines


def write(gen: Path, native: Path, nc: Dict[str, Any], mods: Any = None) -> bool:
    """Writes pyxpo-gen/Info.plist (+ App.entitlements when needed). Returns whether entitlements were written.
    `mods` (config plugins) run after the app config is applied."""
    user = Path(native) / "App" / "Info.plist"
    base = plistlib.loads(user.read_bytes()) if user.is_file() else {}
    plist = info_plist(base, nc)
    ent = entitlements(nc)
    if mods is not None:
        plist, ent = mods.apply_info_plist(plist), mods.apply_entitlements(ent)
    (gen / "Info.plist").write_bytes(plistlib.dumps(plist))
    if ent:
        (gen / "App.entitlements").write_bytes(plistlib.dumps(ent))
    return bool(ent)
