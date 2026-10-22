"""App icons from the app config: an iOS asset catalog and Android adaptive + legacy launcher icons.

Both write only below `pyxpo-gen/`. Nothing is written when no icon is configured, so the platform default stays.
"""
import json
import shutil
from pathlib import Path
from typing import Any, Dict

from ..app_config import colors, images

LEGACY_DPI = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
APPEARANCE = {"dark": "dark", "tinted": "tinted"}
MAC_SIZES = (16, 32, 128, 256, 512)


def _square(src: Path, dst: Path, px: int) -> None:
    """Copies `src` to `dst`, scaling when it is not already px x px."""
    if images.info(src)["width"] == px:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(src), str(dst))
    else:
        images.resize(src, dst, px)


def ios(project: Path, nc: Dict[str, Any], gen: Path) -> bool:
    """Writes pyxpo-gen/runtime/Resources/Assets.xcassets/AppIcon.appiconset (single 1024 size; Xcode derives the rest).

    The light icon is also written in every mac size: a Mac Catalyst build reads CFBundleIconName from Assets.car, and with
    only the iOS entry the catalog holds an iPad rendition alone, so Finder and the Dock show the generic app icon.

    Without an icon the set is written empty: XcodeGen sets ASSETCATALOG_COMPILER_APPICON_NAME=AppIcon on the target,
    and actool fails when the catalog (which splash always writes) has no set of that name."""
    icon = nc["ios"]["icon"]
    cat = Path(gen) / "runtime" / "Resources" / "Assets.xcassets"
    d = cat / "AppIcon.appiconset"
    if d.exists():
        shutil.rmtree(str(d))
    d.mkdir(parents=True)
    (cat / "Contents.json").write_text(json.dumps({"info": {"author": "pyxpo", "version": 1}}, indent=2))
    if not icon.get("light"):
        (d / "Contents.json").write_text(json.dumps({"images": [{"idiom": "universal", "platform": "ios", "size": "1024x1024"}],
                                                     "info": {"author": "pyxpo", "version": 1}}, indent=2))
        return False
    entries = []
    for key in ("light", "dark", "tinted"):
        if not icon.get(key):
            continue
        fname = "icon-%s.png" % key
        _square(Path(project) / icon[key], d / fname, 1024)
        e = {"filename": fname, "idiom": "universal", "platform": "ios", "size": "1024x1024"}
        if key in APPEARANCE:
            e["appearances"] = [{"appearance": "luminosity", "value": APPEARANCE[key]}]
        entries.append(e)
    for size in MAC_SIZES:
        for scale in (1, 2):
            fname = "icon-mac-%d.png" % (size * scale)
            if not (d / fname).exists():
                _square(Path(project) / icon["light"], d / fname, size * scale)
            entries.append({"filename": fname, "idiom": "mac", "scale": "%dx" % scale, "size": "%dx%d" % (size, size)})
    (d / "Contents.json").write_text(json.dumps({"images": entries, "info": {"author": "pyxpo", "version": 1}}, indent=2))
    return True


def _adaptive_xml(bg: str, mono: bool) -> str:
    return ('<?xml version="1.0" encoding="utf-8"?>\n<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
            '    <background android:drawable="@%s" />\n    <foreground android:drawable="@drawable/ic_launcher_foreground" />\n%s'
            '</adaptive-icon>\n' % (bg, '    <monochrome android:drawable="@drawable/ic_launcher_monochrome" />\n' if mono else ""))


def android(project: Path, nc: Dict[str, Any], gen: Path) -> bool:
    """Writes pyxpo-gen/res: adaptive icon (API 26+, themed icon with a monochrome layer) and legacy PNGs (API 24-25)."""
    a = nc["android"]
    ai = a["adaptive_icon"]
    flat = a["icon"]
    if not ai.get("foreground_image") and not flat:
        return False
    project, res = Path(project), Path(gen) / "res"
    if res.exists():
        shutil.rmtree(str(res))
    legacy_src = project / (flat or ai["foreground_image"])
    for dpi, px in LEGACY_DPI.items():
        _square(legacy_src, res / ("mipmap-%s" % dpi) / "ic_launcher.png", px)
        shutil.copyfile(str(res / ("mipmap-%s" % dpi) / "ic_launcher.png"), str(res / ("mipmap-%s" % dpi) / "ic_launcher_round.png"))
    if ai.get("foreground_image"):
        draw = res / "drawable-nodpi"
        draw.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(project / ai["foreground_image"]), str(draw / "ic_launcher_foreground.png"))
        if ai.get("background_image"):
            shutil.copyfile(str(project / ai["background_image"]), str(draw / "ic_launcher_background.png"))
            bg = "drawable/ic_launcher_background"
        else:
            (res / "values").mkdir(parents=True, exist_ok=True)
            (res / "values" / "ic_launcher_background.xml").write_text(
                '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="ic_launcher_background">%s</color>\n</resources>\n'
                % colors.android_argb(ai.get("background_color") or "#FFFFFF"))
            bg = "color/ic_launcher_background"
        mono = bool(ai.get("monochrome_image"))
        if mono:
            shutil.copyfile(str(project / ai["monochrome_image"]), str(draw / "ic_launcher_monochrome.png"))
        v26 = res / "mipmap-anydpi-v26"
        v26.mkdir(parents=True, exist_ok=True)
        for n in ("ic_launcher.xml", "ic_launcher_round.xml"):
            (v26 / n).write_text(_adaptive_xml(bg, mono))
    return True
