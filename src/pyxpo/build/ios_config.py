"""iOS native settings derived from the app config: Info.plist, entitlements, xcconfig keys."""
from __future__ import annotations

import copy
import plistlib
from pathlib import Path
from typing import Any, Dict, List

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


# Required-reason APIs the embedded CPython calls (os.stat, time.monotonic, os.statvfs). Without them App Store
# Connect sends ITMS-91053 on upload.
PYTHON_APIS = {
    "NSPrivacyAccessedAPICategoryFileTimestamp": ["C617.1"],
    "NSPrivacyAccessedAPICategorySystemBootTime": ["35F9.1"],
    "NSPrivacyAccessedAPICategoryDiskSpace": ["E174.1"],
}


def privacy_manifest(nc: Dict[str, Any], parts: List[Dict[str, Any]] = ()) -> Dict[str, Any]:
    """PrivacyInfo.xcprivacy: pyxpo's own entries, then each part (the user's App/PrivacyInfo.xcprivacy, linked modules),
    then `ios.privacy_manifests`. API types merge by type with the reasons joined; lists of domains and data types join."""
    out: Dict[str, Any] = {"NSPrivacyTracking": False, "NSPrivacyTrackingDomains": [], "NSPrivacyCollectedDataTypes": []}
    apis: Dict[str, List[str]] = {k: list(v) for k, v in PYTHON_APIS.items()}
    for part in list(parts) + [nc["ios"].get("privacy_manifests") or {}]:
        for k, v in part.items():
            if k == "NSPrivacyAccessedAPITypes":
                for t in v:
                    have = apis.setdefault(t["NSPrivacyAccessedAPIType"], [])
                    have += [r for r in t.get("NSPrivacyAccessedAPITypeReasons", []) if r not in have]
            elif isinstance(v, list):
                out[k] = list(out.get(k) or []) + [x for x in v if x not in (out.get(k) or [])]
            else:
                out[k] = v
    out["NSPrivacyAccessedAPITypes"] = [{"NSPrivacyAccessedAPIType": t, "NSPrivacyAccessedAPITypeReasons": r}
                                        for t, r in apis.items()]
    return out


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
    # App Store upload refuses an iPad app whose orientations are not all four (iPad multitasking), unless it
    # requires full screen. The template's iPhone list is portrait only, so iPad always gets its own list.
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
    if nc["status_bar"]["hidden"]:
        p["UIStatusBarHidden"] = True  # the launch screen is shown before any code runs, so only the plist can hide it there
    else:
        p.pop("UIStatusBarHidden", None)
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


def write(gen: Path, native: Path, nc: Dict[str, Any], mods: Any = None, privacy: List[Dict[str, Any]] = ()) -> bool:
    """Writes pyxpo-gen/Info.plist, PrivacyInfo.xcprivacy (+ App.entitlements when needed). Returns whether entitlements
    were written. `mods` (config plugins) run after the app config is applied; `privacy` holds the linked modules' entries."""
    user = Path(native) / "App" / "Info.plist"
    base = plistlib.loads(user.read_bytes()) if user.is_file() else {}
    plist = info_plist(base, nc)
    ent = entitlements(nc)
    if mods is not None:
        plist, ent = mods.apply_info_plist(plist), mods.apply_entitlements(ent)
    (gen / "Info.plist").write_bytes(plistlib.dumps(plist))
    user_privacy = Path(native) / "App" / "PrivacyInfo.xcprivacy"
    parts = ([plistlib.loads(user_privacy.read_bytes())] if user_privacy.is_file() else []) + list(privacy or [])
    (gen / "PrivacyInfo.xcprivacy").write_bytes(plistlib.dumps(privacy_manifest(nc, parts)))
    if ent:
        (gen / "App.entitlements").write_bytes(plistlib.dumps(ent))
    return bool(ent)
