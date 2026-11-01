"""Android side of the app config: generated Gradle script, overlay manifests and values.

Everything lands in `pyxpo-gen/` (rewritten on every build). The user-owned `AndroidManifest.xml` and
`build.gradle.kts` stay as they are. The generated manifests sit on the `debug` and `release` source sets, which the
manifest merger ranks above `main`, so their attributes win (`tools:replace` states it for attributes `main` sets).
"""
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import quoteattr

from .. import config_plugins
from ..app_config import colors
from . import icons, splash

ORIENT = {"default": None, "portrait": "portrait", "landscape": "landscape"}
KEYBOARD = {"resize": "adjustResize", "pan": "adjustPan"}
NS = ('xmlns:android="http://schemas.android.com/apk/res/android" '
      'xmlns:tools="http://schemas.android.com/tools"')
ACTIVITY = "dev.pyxpo.runtime.MainActivity"


def _pick(d: Dict[str, Any], *names: str) -> Any:
    for n in names:
        if n in d:
            return d[n]
    return None


def _action(a: str) -> str:
    return a if "." in a else "android.intent.action.%s" % a


def _category(c: str) -> str:
    return c if "." in c else "android.intent.category.%s" % c


def intent_filter_xml(f: Dict[str, Any]) -> str:
    """Expo shape: {action, autoVerify, data: [{scheme, host, pathPrefix, ...}], category: [...]}."""
    attrs = ' android:autoVerify="true"' if _pick(f, "auto_verify", "autoVerify") else ""
    out = ["            <intent-filter%s>" % attrs, '                <action android:name=%s />' % quoteattr(_action(str(f.get("action", "VIEW"))))]
    cats = f.get("category") or []
    for c in [cats] if isinstance(cats, str) else cats:
        out.append('                <category android:name=%s />' % quoteattr(_category(str(c))))
    data = f.get("data") or []
    for d in [data] if isinstance(data, dict) else data:
        parts = []
        for xml_name, keys in (("scheme", ("scheme",)), ("host", ("host",)), ("port", ("port",)), ("path", ("path",)),
                               ("pathPrefix", ("path_prefix", "pathPrefix")), ("pathPattern", ("path_pattern", "pathPattern")),
                               ("mimeType", ("mime_type", "mimeType"))):
            v = _pick(d, *keys)
            if v is not None:
                parts.append("android:%s=%s" % (xml_name, quoteattr(str(v))))
        out.append("                <data %s />" % " ".join(parts))
    out.append("            </intent-filter>")
    return "\n".join(out)


def scheme_filter_xml(schemes: List[str]) -> str:
    out = ["            <intent-filter>", '                <action android:name="android.intent.action.VIEW" />',
           '                <category android:name="android.intent.category.DEFAULT" />',
           '                <category android:name="android.intent.category.BROWSABLE" />']
    out += ['                <data android:scheme=%s />' % quoteattr(s) for s in schemes]
    out.append("            </intent-filter>")
    return "\n".join(out)


def meta_data(nc: Dict[str, Any]) -> List[str]:
    """`pyxpo.*` application meta-data read by the runtime (`PxAppConfig`). Colors use "argb:" so aapt keeps them strings."""
    a, sb, nb = nc["android"], nc["status_bar"], nc["navigation_bar"]
    values = {"pyxpo.background_color": "argb:" + colors.android_argb(a["background_color"])[1:],
              "pyxpo.user_interface_style": a["user_interface_style"],
              "pyxpo.status_bar_style": sb["style"], "pyxpo.status_bar_hidden": str(bool(sb["hidden"])).lower(),
              "pyxpo.navigation_bar_style": nb["style"], "pyxpo.navigation_bar_hidden": str(bool(nb["hidden"])).lower(),
              "pyxpo.splash_image_width": str(a["splash"]["image_width"])}
    return ['        <meta-data android:name=%s android:value=%s />' % (quoteattr(k), quoteattr(v)) for k, v in values.items()]


def manifest(nc: Dict[str, Any], debug: bool, icon: bool = False, splash_theme: bool = False) -> str:
    a = nc["android"]
    cleartext = a["uses_cleartext_traffic"]
    if cleartext is None:
        cleartext = debug  # dev server and hot reload speak plain HTTP; release must opt in
    perms = ['    <uses-permission android:name=%s />' % quoteattr(p) for p in a["permissions"]]
    perms += ['    <uses-permission android:name=%s tools:node="remove" />' % quoteattr(p) for p in a["blocked_permissions"]]
    app = ['android:allowBackup="%s"' % str(bool(a["allow_backup"])).lower(),
           'android:usesCleartextTraffic="%s"' % str(bool(cleartext)).lower()]
    replace = ["android:allowBackup", "android:usesCleartextTraffic"]
    if icon:
        app += ['android:icon="@mipmap/ic_launcher"', 'android:roundIcon="@mipmap/ic_launcher_round"']
    if a["predictive_back_gesture_enabled"]:
        app.append('android:enableOnBackInvokedCallback="true"')
    act = ['android:name="%s"' % ACTIVITY, 'android:windowSoftInputMode="%s"' % KEYBOARD[a["software_keyboard_layout_mode"]]]
    act_replace = ["android:windowSoftInputMode"]
    if splash_theme:
        act.append('android:theme="@style/PyxpoSplash"')
        act_replace.append("android:theme")
    if ORIENT.get(a["orientation"]):
        act.append('android:screenOrientation="%s"' % ORIENT[a["orientation"]])
    filters = [scheme_filter_xml(nc["schemes"])] + [intent_filter_xml(f) for f in a["intent_filters"]]
    lines = ['<?xml version="1.0" encoding="utf-8"?>', "<!-- Generated by pyxpo from [tool.pyxpo]. Edit pyproject.toml, not this file. -->",
             "<manifest %s>" % NS] + perms + [
        "    <application %s" % " ".join(app), '        tools:replace="%s">' % ",".join(replace),
        ] + meta_data(nc) + [
        "        <activity %s" % " ".join(act), '            tools:replace="%s">' % ",".join(act_replace)] + filters + [
        "        </activity>", "    </application>", "</manifest>", ""]
    return "\n".join(lines)


def gradle(nc: Dict[str, Any], res: bool = False, extra: List[str] = None) -> str:
    """Groovy script applied from the user's app/build.gradle.kts (overrides what it set)."""
    a = nc["android"]
    return "\n".join([
        "// Generated by pyxpo from [tool.pyxpo]. Edit pyproject.toml, not this file.",
        "android {",
        "    compileSdk %d" % a["compile_sdk"],
        "    defaultConfig {",
        "        minSdk %d" % a["min_sdk"],
        "        targetSdk %d" % a["target_sdk"],
        "    }",
        "    sourceSets {",
        ] + (['        main.res.srcDir "${rootDir}/pyxpo-gen/res"'] if res else []) + [
        "        debug.manifest.srcFile \"${rootDir}/pyxpo-gen/manifest/debug/AndroidManifest.xml\"",
        "        release.manifest.srcFile \"${rootDir}/pyxpo-gen/manifest/release/AndroidManifest.xml\"",
        "        debug.assets.srcDir \"${rootDir}/pyxpo-gen/app-debug\"",
        "        release.assets.srcDir \"${rootDir}/pyxpo-gen/app-release\"",
        "    }",
        ] + _build_properties(a["build_properties"]) + [
        "}"] + list(extra or []) + [""])


PROGUARD = "proguard-rules.pro"
# R8 keeps what C calls by name over JNI (pyxpo_jni.c, pyxpo_layout_jni.c) and what is found by reflection.
# Module packages add their own rules with a proguard-rules.pro in their android/ folder.
KEEP_RULES = [
    "-keepclasseswithmembernames,includedescriptorclasses class * { native <methods>; }",
    "-keep class dev.pyxpo.runtime.PyxpoRuntime { void onOps(java.lang.String); }",
    "-keep class dev.pyxpo.runtime.NativeLayout { long measure(int, float, int, float, int); }",
    "# PxProcess.start finds this by reflection (module-api PxModule.kt).",
    "-keep class dev.pyxpo.runtime.PyxpoRuntime { public static void startHeadless(android.content.Context); }",
    "# Keeps line numbers in Play crash reports; the mapping file in the AAB restores the names.",
    "-keepattributes SourceFile,LineNumberTable",
    "-renamesourcefileattribute SourceFile",
]


def _q(s: str) -> str:
    return "'%s'" % s.replace("\\", "\\\\").replace("'", "\\'")


def _build_properties(bp: Dict[str, Any]) -> List[str]:
    """`build_properties.android` as Groovy inside `android { }`. Applied after the app's own `android { }`, so these
    win, and an ejected `build.gradle.kts` gets them too."""
    out = ["    buildTypes {", "        release {", "            minifyEnabled %s" % str(bool(bp["minify"])).lower(),
           "            shrinkResources %s" % str(bool(bp["shrink"])).lower()]
    if bp["minify"]:
        out.append("            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), "
                   '"${rootDir}/pyxpo-gen/%s"' % PROGUARD)
    if bp["debug_symbol_level"] != "none":
        out.append("            ndk { debugSymbolLevel '%s' }" % bp["debug_symbol_level"].upper())
    out += ["        }", "    }"]
    if bp["pick_first"] or bp["exclude"]:
        out.append("    packagingOptions {")
        out += ["        resources.pickFirsts.add(%s)" % _q(p) for p in bp["pick_first"]]
        out += ["        resources.excludes.add(%s)" % _q(p) for p in bp["exclude"]]
        out.append("    }")
    return out


def proguard_text(nc: Dict[str, Any]) -> str:
    rules = nc["android"]["build_properties"]["proguard_rules"].strip()
    return ("# Generated by pyxpo on every build. Add rules with [tool.pyxpo.build_properties.android] extra_proguard_rules.\n"
            + "\n".join(KEEP_RULES) + "\n" + (rules + "\n" if rules else ""))


def write(gen: Path, nc: Dict[str, Any], project: Path, mods: Any = None) -> None:
    gen = Path(gen)
    if (gen / "res").exists():
        shutil.rmtree(str(gen / "res"))
    icon = icons.android(project, nc, gen)
    themed = splash.android(project, nc, gen)["theme"]
    mods = mods or config_plugins.Mods()
    values = mods.apply_res_values({})
    if values:
        (gen / "res" / "values").mkdir(parents=True, exist_ok=True)
        (gen / "res" / "values" / "pyxpo_plugins.xml").write_text(config_plugins.res_values_xml(values))
    for kind in ("debug", "release"):
        d = gen / "manifest" / kind
        d.mkdir(parents=True, exist_ok=True)
        (d / "AndroidManifest.xml").write_text(mods.apply_manifest(manifest(nc, kind == "debug", icon, themed)))
    keep = nc["android"]["build_properties"]["shrink"]
    if keep:  # the runtime finds these by name (AppConfig.kt), which resource shrinking cannot see
        (gen / "res" / "raw").mkdir(parents=True, exist_ok=True)
        (gen / "res" / "raw" / "pyxpo_keep.xml").write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n<resources xmlns:tools="http://schemas.android.com/tools"\n'
            '    tools:keep="@color/pyxpo_splash_*,@drawable/pyxpo_splash_*,@mipmap/ic_launcher*" />\n')
    (gen / PROGUARD).write_text(proguard_text(nc))
    (gen / "pyxpo.app.gradle").write_text(gradle(nc, icon or themed or bool(values) or keep, mods.apply_app_gradle([])))


MARK_BEGIN, MARK_END = "# >>> pyxpo config plugins (generated, do not edit) >>>", "# <<< pyxpo config plugins <<<"


def write_gradle_properties(native: Path, mods: Any, base: Optional[Dict[str, str]] = None) -> None:
    """Keeps a marked block in the user-owned `android/gradle.properties` in step with `with_gradle_properties` mods.
    `base` holds properties the linked modules need; the mods see and may change them."""
    props = mods.apply_gradle_properties(dict(base or {}))
    f = Path(native) / "gradle.properties"
    text = f.read_text() if f.is_file() else ""
    if MARK_BEGIN in text and MARK_END in text:
        head, rest = text.split(MARK_BEGIN, 1)
        text = head.rstrip("\n") + ("\n" if head.strip() else "") + rest.split(MARK_END, 1)[1].lstrip("\n")
    if props:
        block = "\n".join([MARK_BEGIN] + ["%s=%s" % (k, v) for k, v in props.items()] + [MARK_END]) + "\n"
        text = (text.rstrip("\n") + "\n\n" if text.strip() else "") + block
    if props or f.is_file():
        f.write_text(text)
