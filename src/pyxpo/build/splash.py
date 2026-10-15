"""Splash screen from the app config: iOS launch screen assets and Android splash theme resources.

Both write only below `pyxpo-gen/`. The static launch screen is shown by the OS before any code runs; the runtime keeps an
overlay with the same look until the first frame (or `SplashScreen.hide()` after `prevent_auto_hide()`).
"""
import json
import shutil
from pathlib import Path
from typing import Any, Dict

from ..app_config import colors, images

SCALE = 3  # iOS launch image is stored as a 3x asset, so its point size is width_px / 3


def _colorset(d: Path, light: str, dark: str = None) -> None:
    def entry(c: str, appearance: str = None) -> Dict[str, Any]:
        e: Dict[str, Any] = {"color": {"color-space": "srgb", "components": colors.components(c)}, "idiom": "universal"}
        if appearance:
            e["appearances"] = [{"appearance": "luminosity", "value": appearance}]
        return e
    d.mkdir(parents=True, exist_ok=True)
    items = [entry(light)] + ([entry(dark, "dark")] if dark else [])
    (d / "Contents.json").write_text(json.dumps({"colors": items, "info": {"author": "pyxpo", "version": 1}}, indent=2))


def _scaled(project: Path, rel: str, dst: Path, width_px: int) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if images.info(project / rel)["width"] == width_px:
        shutil.copyfile(str(project / rel), str(dst))
    else:
        images.resize_width(project / rel, dst, width_px)


def ios(project: Path, nc: Dict[str, Any], gen: Path) -> bool:
    """Writes SplashBackground.colorset (always) and SplashImage.imageset (when an image is set) into the asset catalog."""
    s = nc["ios"]["splash"]
    cat = Path(gen) / "runtime" / "Resources" / "Assets.xcassets"
    cat.mkdir(parents=True, exist_ok=True)
    (cat / "Contents.json").write_text(json.dumps({"info": {"author": "pyxpo", "version": 1}}, indent=2))
    _colorset(cat / "SplashBackground.colorset", s["background_color"], s.get("dark_background_color"))
    d = cat / "SplashImage.imageset"
    if d.exists():
        shutil.rmtree(str(d))
    if not s.get("image"):
        return False
    d.mkdir(parents=True)
    width = int(s["image_width"]) * SCALE
    entries = []
    for key, rel in (("light", s["image"]), ("dark", s.get("dark_image"))):
        if not rel:
            continue
        fname = "splash-%s.png" % key
        _scaled(Path(project), rel, d / fname, width)
        e = {"filename": fname, "idiom": "universal", "scale": "%dx" % SCALE}
        if key == "dark":
            e["appearances"] = [{"appearance": "luminosity", "value": "dark"}]
        entries.append(e)
    (d / "Contents.json").write_text(json.dumps({"images": entries, "info": {"author": "pyxpo", "version": 1}}, indent=2))
    return True


def _values(name: str, color: str) -> str:
    return '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="%s">%s</color>\n</resources>\n' % (name, colors.android_argb(color))


def android(project: Path, nc: Dict[str, Any], gen: Path) -> Dict[str, Any]:
    """Writes pyxpo-gen/res/{values,values-night,values-v31,drawable-nodpi,drawable}. Returns {"theme": bool} for the manifest.

    Resources: `pyxpo_splash_bg` color (+ night), `pyxpo_splash_image` drawable (+ night variant), the `PyxpoSplash` theme.
    Android 12+ uses the system splash (background + animated icon); older versions use a layer-list window background.
    """
    s = nc["android"]["splash"]
    project, res = Path(project), Path(gen) / "res"
    dark_bg = s.get("dark_background_color") or (s["background_color"] if s.get("dark_image") else None)
    for d, bg in (("values", s["background_color"]), ("values-night", dark_bg)):
        if bg:
            (res / d).mkdir(parents=True, exist_ok=True)
            (res / d / "pyxpo_splash_bg.xml").write_text(_values("pyxpo_splash_bg", bg))
    img = s.get("image")
    if img:
        (res / "drawable-nodpi").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(project / img), str(res / "drawable-nodpi" / "pyxpo_splash_image.png"))
        if s.get("dark_image"):
            (res / "drawable-night-nodpi").mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(project / s["dark_image"]), str(res / "drawable-night-nodpi" / "pyxpo_splash_image.png"))
        w, h = images.info(project / img)["width"], images.info(project / img)["height"]
        dp_w = int(s["image_width"])
        dp_h = max(1, round(dp_w * h / w))
        win = ('<?xml version="1.0" encoding="utf-8"?>\n<layer-list xmlns:android="http://schemas.android.com/apk/res/android">\n'
               '    <item android:drawable="@color/pyxpo_splash_bg" />\n'
               '    <item android:width="%ddp" android:height="%ddp" android:gravity="center">\n'
               '        <bitmap android:src="@drawable/pyxpo_splash_image" android:gravity="fill" />\n    </item>\n</layer-list>\n' % (dp_w, dp_h))
    else:
        win = None
    (res / "drawable").mkdir(parents=True, exist_ok=True)
    (res / "drawable" / "pyxpo_splash_window.xml").write_text(win or (
        '<?xml version="1.0" encoding="utf-8"?>\n<color xmlns:android="http://schemas.android.com/apk/res/android" android:color="@color/pyxpo_splash_bg" />\n'))
    base = "android:Theme.DeviceDefault.Light.NoActionBar"
    (res / "values" / "pyxpo_splash_theme.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <style name="PyxpoSplash" parent="%s">\n'
        '        <item name="android:windowBackground">@drawable/pyxpo_splash_window</item>\n    </style>\n</resources>\n' % base)
    (res / "values-night").mkdir(parents=True, exist_ok=True)
    (res / "values-night" / "pyxpo_splash_theme.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <style name="PyxpoSplash" parent="android:Theme.DeviceDefault.NoActionBar">\n'
        '        <item name="android:windowBackground">@drawable/pyxpo_splash_window</item>\n    </style>\n</resources>\n')
    (res / "values-v31").mkdir(parents=True, exist_ok=True)
    extra = '        <item name="android:windowSplashScreenAnimatedIcon">@drawable/pyxpo_splash_image</item>\n' if img else ""
    (res / "values-v31" / "pyxpo_splash_theme.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <style name="PyxpoSplash" parent="android:Theme.DeviceDefault.Light.NoActionBar">\n'
        '        <item name="android:windowSplashScreenBackground">@color/pyxpo_splash_bg</item>\n%s    </style>\n</resources>\n' % extra)
    (res / "values-night-v31").mkdir(parents=True, exist_ok=True)
    (res / "values-night-v31" / "pyxpo_splash_theme.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <style name="PyxpoSplash" parent="android:Theme.DeviceDefault.NoActionBar">\n'
        '        <item name="android:windowSplashScreenBackground">@color/pyxpo_splash_bg</item>\n%s    </style>\n</resources>\n' % extra)
    return {"theme": True}
