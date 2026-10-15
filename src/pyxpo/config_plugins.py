"""Config plugins: Python hooks that change the generated native config, like Expo config plugins and mods.

List them in `[tool.pyxpo] plugins`: `"./plugins/foo.py"`, `"pkg.mod"`, `"pkg.mod:fn"` or `["entry", {options}]`.
A plugin is `plugin(config, props)`; it registers mods with the `with_*` helpers and returns `config`.
A mod gets the data to change (a dict, an XML root, ...), mutates it in place or returns a replacement.
Mods run at build time, after the app config is applied, and only touch generated files (`pyxpo-gen/`),
except `with_gradle_properties` (a marked block in `android/gradle.properties`) and `with_dangerous_mod`.
"""
from __future__ import annotations

import copy
import importlib
import importlib.util
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .app_config import ConfigError

ANDROID_NS = "http://schemas.android.com/apk/res/android"
TOOLS_NS = "http://schemas.android.com/tools"
DEFAULT_FN = "plugin"
RES_TYPES = ("string", "color", "integer", "bool", "dimen")


def android_name(attr: str) -> str:
    """ElementTree name of an `android:` attribute: `el.set(android_name("name"), "x")`."""
    return "{%s}%s" % (ANDROID_NS, attr)


def tools_name(attr: str) -> str:
    return "{%s}%s" % (TOOLS_NS, attr)


class Mods:
    """What the plugins registered. Each `apply_*` runs the mods for one target in registration order."""

    def __init__(self) -> None:
        self.info_plist: List[Callable] = []
        self.entitlements: List[Callable] = []
        self.xcconfig: List[Callable] = []
        self.android_manifest: List[Callable] = []
        self.gradle_properties: List[Callable] = []
        self.app_gradle: List[Callable] = []
        self.android_res_values: List[Callable] = []
        self.dangerous: List[Tuple[str, Callable]] = []

    def _run(self, fns: List[Callable], data: Any) -> Any:
        for fn in fns:
            out = fn(data)
            if out is not None:
                data = out
        return data

    def apply_info_plist(self, d: Dict[str, Any]) -> Dict[str, Any]:
        return self._run(self.info_plist, d)

    def apply_entitlements(self, d: Dict[str, Any]) -> Dict[str, Any]:
        return self._run(self.entitlements, d)

    def apply_xcconfig(self, d: Dict[str, str]) -> Dict[str, str]:
        return self._run(self.xcconfig, d)

    def apply_gradle_properties(self, d: Dict[str, str]) -> Dict[str, str]:
        return self._run(self.gradle_properties, d)

    def apply_app_gradle(self, lines: List[str]) -> List[str]:
        return self._run(self.app_gradle, lines)

    def apply_res_values(self, d: Dict[str, Tuple[str, str]]) -> Dict[str, Tuple[str, str]]:
        return self._run(self.android_res_values, d)

    def apply_manifest(self, text: str) -> str:
        """Runs the manifest mods over the XML text and returns the new text."""
        if not self.android_manifest:
            return text
        ET.register_namespace("android", ANDROID_NS)
        ET.register_namespace("tools", TOOLS_NS)
        root = ET.fromstring(text)
        root = self._run(self.android_manifest, root)
        ET.indent(root)
        head = text.split("<manifest", 1)[0]
        return head + ET.tostring(root, encoding="unicode") + "\n"

    def run_dangerous(self, platform: str, project: Path, native: Path) -> None:
        for plat, fn in self.dangerous:
            if plat in (platform, "all"):
                fn(DangerousContext(platform, Path(project), Path(native)))

    def empty(self) -> bool:
        return not any([self.info_plist, self.entitlements, self.xcconfig, self.android_manifest, self.gradle_properties,
                        self.app_gradle, self.android_res_values, self.dangerous])


class DangerousContext:
    """Passed to `with_dangerous_mod` functions: raw access to the project and the ejected native folder."""

    def __init__(self, platform: str, project: Path, native: Path) -> None:
        self.platform, self.project, self.native = platform, project, native


class PluginConfig:
    """First argument of a plugin: read-only `native` values (a copy), the project path, and the mods registry."""

    def __init__(self, nc: Dict[str, Any], project: Path, mods: Mods) -> None:
        self.native, self.project, self.mods = copy.deepcopy(nc), Path(project), mods


def _register(config: PluginConfig, kind: str, fn: Callable) -> PluginConfig:
    if not callable(fn):
        raise ConfigError("config plugin: with_%s needs a function, got %r" % (kind, fn))
    getattr(config.mods, kind).append(fn)
    return config


def with_info_plist(config: PluginConfig, fn: Callable[[Dict[str, Any]], Any]) -> PluginConfig:
    """iOS: `fn(plist_dict)` on the generated Info.plist content."""
    return _register(config, "info_plist", fn)


def with_entitlements(config: PluginConfig, fn: Callable[[Dict[str, Any]], Any]) -> PluginConfig:
    """iOS: `fn(dict)` on the entitlements; the file is written when the result is not empty."""
    return _register(config, "entitlements", fn)


def with_xcconfig(config: PluginConfig, fn: Callable[[Dict[str, str]], Any]) -> PluginConfig:
    """iOS: `fn(dict)` on extra Xcode build settings, written after the generated ones (so they win)."""
    return _register(config, "xcconfig", fn)


def with_android_manifest(config: PluginConfig, fn: Callable[[ET.Element], Any]) -> PluginConfig:
    """Android: `fn(root)` on the generated overlay manifest (debug and release). Use `android_name`/`tools_name`."""
    return _register(config, "android_manifest", fn)


def with_gradle_properties(config: PluginConfig, fn: Callable[[Dict[str, str]], Any]) -> PluginConfig:
    """Android: `fn(dict)` on properties written to a marked block of `android/gradle.properties`."""
    return _register(config, "gradle_properties", fn)


def with_app_gradle(config: PluginConfig, fn: Callable[[List[str]], Any]) -> PluginConfig:
    """Android: `fn(lines)` on the Groovy lines appended to the generated `pyxpo.app.gradle`."""
    return _register(config, "app_gradle", fn)


def with_android_res_values(config: PluginConfig, fn: Callable[[Dict[str, Tuple[str, str]]], Any]) -> PluginConfig:
    """Android: `fn(dict)` where the dict maps a resource name to (type, value); type is string, color, integer, bool or dimen."""
    return _register(config, "android_res_values", fn)


def with_dangerous_mod(config: PluginConfig, platform: str, fn: Callable[[DangerousContext], Any]) -> PluginConfig:
    """Run `fn(ctx)` after the native folder is generated. `platform` is 'ios', 'android' or 'all'. No safety net."""
    if platform not in ("ios", "android", "all"):
        raise ConfigError("config plugin: with_dangerous_mod platform must be ios, android or all, got %r" % (platform,))
    if not callable(fn):
        raise ConfigError("config plugin: with_dangerous_mod needs a function, got %r" % (fn,))
    config.mods.dangerous.append((platform, fn))
    return config


def _resolve(entry: str, project: Path) -> Callable:
    mod_part, _, fn_name = entry.partition(":")
    fn_name = fn_name or DEFAULT_FN
    if mod_part.endswith(".py") or "/" in mod_part:
        f = (project / mod_part).resolve()
        if not f.is_file():
            raise ConfigError("plugins: file not found: %s" % f)
        spec = importlib.util.spec_from_file_location("_pyxpo_plugin_%s" % f.stem, str(f))
        mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(f.parent))
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.path.remove(str(f.parent))
    else:
        sys.path.insert(0, str(project))
        try:
            mod = importlib.import_module(mod_part)
        except ImportError as e:
            raise ConfigError("plugins: cannot import %r: %s" % (mod_part, e))
        finally:
            sys.path.remove(str(project))
    fn = getattr(mod, fn_name, None)
    if not callable(fn):
        raise ConfigError("plugins: %r has no function %r (a plugin is plugin(config, props))" % (mod_part, fn_name))
    return fn


def load(nc: Dict[str, Any], project: Optional[Path]) -> Mods:
    """Runs every plugin listed in the config and returns the registered mods."""
    mods = Mods()
    if project is None or not nc.get("plugins"):
        return mods
    project = Path(project)
    for item in nc["plugins"]:
        entry, props = (item, {}) if isinstance(item, str) else (item[0], item[1] if len(item) > 1 else {})
        if not isinstance(entry, str) or not isinstance(props, dict):
            raise ConfigError("plugins: expected 'entry' or ['entry', {options}], got %r" % (item,))
        fn = _resolve(entry, project)
        try:
            out = fn(PluginConfig(nc, project, mods), dict(props))
        except ConfigError:
            raise
        except Exception as e:  # noqa: BLE001  (a plugin is user code)
            raise ConfigError("plugin %r failed: %s: %s" % (entry, type(e).__name__, e))
        if out is not None and not isinstance(out, PluginConfig):
            raise ConfigError("plugin %r must return the config it was given (or nothing)" % entry)
    return mods


def res_values_xml(values: Dict[str, Tuple[str, str]]) -> str:
    from xml.sax.saxutils import escape
    out = ['<?xml version="1.0" encoding="utf-8"?>', "<!-- Generated by pyxpo config plugins. -->", "<resources>"]
    for name, (kind, value) in sorted(values.items()):
        if kind not in RES_TYPES:
            raise ConfigError("android res value %r: type must be one of %s, got %r" % (name, ", ".join(RES_TYPES), kind))
        v = str(value).lower() if kind == "bool" else escape(str(value))
        if kind == "string":
            v = v.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
        out.append('    <%s name="%s">%s</%s>' % (kind, name, v, kind))
    out.append("</resources>\n")
    return "\n".join(out)
