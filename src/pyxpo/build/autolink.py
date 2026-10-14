"""Native module autolinking: only the modules an app lists in `[tool.pyxpo] modules` are compiled into it.

A module is a package with `pyxpo-module.json`, Python code, and optional `ios/*.swift` and
`android/src/main/**` sources. First-party modules live in `pyxpo/modules/`; third-party ones are pip
packages exposing the `pyxpo.modules` entry point. Unlisted modules are never copied, so they add no code,
permissions or dependencies to the app.
"""
from __future__ import annotations

import ast
import difflib
import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from .runtime import BuildError

MODULES_DIR = Path(__file__).resolve().parent.parent / "modules"
META = "pyxpo-module.json"
NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
CLASS_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
SETTINGS_LINE = 'apply(from = "pyxpo-gen/modules.settings.gradle.kts")'
APP_LINE = 'apply(from = "../pyxpo-gen/modules.app.gradle.kts")'


class Module:
    def __init__(self, root: Path, meta: Dict[str, Any], pkg: str) -> None:
        self.root, self.meta, self.pkg = root, meta, pkg
        self.name: str = meta["name"]
        self.native: str = meta["native"]
        self.ios: Dict[str, Any] = meta.get("ios") or {}
        self.android: Dict[str, Any] = meta.get("android") or {}

    def __repr__(self) -> str:
        return "Module(%s)" % self.name


def validate(meta: Any, where: str) -> Dict[str, Any]:
    def bad(msg: str) -> BuildError:
        return BuildError("%s: %s" % (where, msg))

    if not isinstance(meta, dict):
        raise bad("must be a JSON object")
    name, native = meta.get("name"), meta.get("native")
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise bad("'name' must be lowercase letters, digits and dashes")
    if not isinstance(native, str) or not re.match(r"^[A-Z][A-Za-z0-9]*$", native):
        raise bad("'native' (the bridge module name) must be a CapitalizedName")
    ios, android = meta.get("ios") or {}, meta.get("android") or {}
    for plat, spec in (("ios", ios), ("android", android)):
        classes = spec.get("classes", [])
        if plat in meta and (not isinstance(classes, list) or not classes
                             or not all(isinstance(c, str) and CLASS_RE.match(c) for c in classes)):
            raise bad("%s.classes must be a non-empty list of class names" % plat)
    if "android" in meta and not re.match(r"^[a-z][a-z0-9_.]*$", str(android.get("namespace", ""))):
        raise bad("android.namespace is required (for example dev.pyxpo.modules.mine)")
    for key, spec in (ios.get("infoPlist") or {}).items():
        if not isinstance(spec, dict) or "default" not in spec:
            raise bad("ios.infoPlist.%s needs a 'default'" % key)
    return meta


def _load(root: Path, pkg: str) -> Optional[Module]:
    f = root / META
    if not f.is_file():
        return None
    try:
        meta = json.loads(f.read_text())
    except ValueError as e:
        raise BuildError("%s: invalid JSON (%s)" % (f, e))
    return Module(root, validate(meta, str(f)), pkg)


def _entry_points() -> List[Any]:
    try:
        from importlib import metadata
        eps = metadata.entry_points()
        return list(eps.select(group="pyxpo.modules")) if hasattr(eps, "select") else list(eps.get("pyxpo.modules", []))
    except Exception:  # noqa: BLE001
        return []


def discover() -> Dict[str, Module]:
    """{module name: Module} for first-party modules plus installed third-party ones."""
    found: Dict[str, Module] = {}
    if MODULES_DIR.is_dir():
        for d in sorted(MODULES_DIR.iterdir()):
            m = _load(d, "pyxpo.modules." + d.name) if d.is_dir() else None
            if m:
                found[m.name] = m
    for ep in _entry_points():
        try:
            mod = ep.load()
        except Exception as e:  # noqa: BLE001
            raise BuildError("cannot load native module entry point %r: %s" % (ep.name, e))
        m = _load(Path(mod.__file__).parent, mod.__name__)
        if m is None:
            raise BuildError("module package %s has no %s" % (mod.__name__, META))
        if m.name in found:
            raise BuildError("native module name %r is provided twice" % m.name)
        found[m.name] = m
    return found


def imported_modules(project: Path, known: Dict[str, Module]) -> Dict[str, str]:
    """{module name: 'file:line'} for modules the app's Python code imports."""
    by_pkg = {m.pkg: m.name for m in known.values()}
    used: Dict[str, str] = {}
    app = Path(project) / "app"
    for f in sorted(app.rglob("*.py")) if app.is_dir() else []:
        try:
            tree = ast.parse(f.read_text(), str(f))
        except (SyntaxError, ValueError, OSError):
            continue
        for node in ast.walk(tree):
            names: List[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module] + ["%s.%s" % (node.module, a.name) for a in node.names]
            for n in names:
                for pkg, mod in by_pkg.items():
                    if n == pkg or n.startswith(pkg + "."):
                        used.setdefault(mod, "%s:%d" % (f.relative_to(project), node.lineno))
    return used


def resolve(cfg: Dict[str, Any], project: Path, known: Optional[Dict[str, Module]] = None) -> List[Module]:
    """The modules to link, in config order. Fails when the app imports a module it did not list."""
    known = discover() if known is None else known
    listed = cfg.get("modules", [])
    if not isinstance(listed, list) or not all(isinstance(n, str) for n in listed):
        raise BuildError("[tool.pyxpo] modules must be a list of module names")
    out: List[Module] = []
    for n in listed:
        if n not in known:
            close = difflib.get_close_matches(n, list(known), n=3)
            raise BuildError("unknown native module %r in [tool.pyxpo] modules%s (available: %s)" % (
                n, "; did you mean %s?" % " or ".join(repr(c) for c in close) if close else "",
                ", ".join(sorted(known)) or "none"))
        if known[n] not in out:
            out.append(known[n])
    for name, where in imported_modules(project, known).items():
        if name not in listed:
            raise BuildError("%s imports native module %r but it is not linked: add %r to [tool.pyxpo] modules "
                             "in pyproject.toml" % (where, name, name))
    return out


def info_plist(mods: List[Module], options: Dict[str, Any]) -> Dict[str, str]:
    """Usage-description keys the linked modules need. `options` is `[tool.pyxpo.module_options.<module>]`."""
    keys: Dict[str, str] = {}
    for m in mods:
        opts = (options or {}).get(m.name) or {}
        for key, spec in (m.ios.get("infoPlist") or {}).items():
            keys.setdefault(key, str(opts.get(spec.get("option", ""), spec["default"])))
    return keys


def _plist_xml(entries: Dict[str, str]) -> str:
    from xml.sax.saxutils import escape
    body = "".join("\t<key>%s</key>\n\t<string>%s</string>\n" % (escape(k), escape(v)) for k, v in sorted(entries.items()))
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0">\n<dict>\n%s</dict>\n</plist>\n' % body)


def registry_swift(mods: List[Module]) -> str:
    classes = [c for m in mods for c in m.ios.get("classes", [])]
    return ("// Generated by pyxpo: the native modules linked into this app.\n"
            "let pxModules: [PxModule.Type] = [%s]\n" % ", ".join(c + ".self" for c in classes))


def registry_kotlin(mods: List[Module]) -> str:
    classes = [c for m in mods for c in m.android.get("classes", [])]
    return ("// Generated by pyxpo: the native modules linked into this app.\n"
            "package dev.pyxpo.runtime\n\nimport dev.pyxpo.moduleapi.PxModule\n\n"
            "val pxModules: List<PxModule> = listOf(%s)\n" % ", ".join(c + "()" for c in classes))


def render_ios(gen: Path, mods: List[Module], options: Optional[Dict[str, Any]] = None) -> None:
    """Copies linked modules' Swift into `pyxpo-gen/runtime/modules/` and writes the registry and Info.plist keys."""
    out = gen / "runtime" / "modules"
    if out.exists():
        shutil.rmtree(str(out))
    out.mkdir(parents=True)
    for m in mods:
        src = m.root / "ios"
        if src.is_dir():
            for f in sorted(src.rglob("*.swift")):
                dst = out / m.name / f.relative_to(src)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(f), str(dst))
    (out / "PxModuleRegistry.swift").write_text(registry_swift([m for m in mods if m.ios]))
    (gen / "ModulesInfo.plist").write_text(_plist_xml(info_plist(mods, options or {})))


def _gradle_str(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$")


def module_gradle(m: Module) -> str:
    deps = "".join('    implementation("%s")\n' % _gradle_str(d) for d in m.android.get("dependencies", []))
    return ('plugins {\n    id("com.android.library")\n    id("org.jetbrains.kotlin.android")\n}\n\n'
            'android {\n    namespace = "%s"\n    compileSdk = 35\n    defaultConfig { minSdk = %d }\n'
            '    compileOptions {\n        sourceCompatibility = JavaVersion.VERSION_17\n'
            '        targetCompatibility = JavaVersion.VERSION_17\n    }\n    kotlinOptions { jvmTarget = "17" }\n}\n\n'
            'dependencies {\n    implementation(project(":px-module-api"))\n%s}\n'
            % (m.android["namespace"], int(m.android.get("minSdk", 24)), deps))


def render_android(gen: Path, mods: List[Module]) -> None:
    """Writes one Gradle library per linked module plus the settings/app fragments and the Kotlin registry.
    The Gradle manifest merger then brings each module's permissions and providers into the app."""
    droid = [m for m in mods if m.android]
    root = gen / "modules"
    if root.exists():
        shutil.rmtree(str(root))
    includes = ['include(":px-module-api")', 'project(":px-module-api").projectDir = file("pyxpo-gen/module-api")']
    deps = ['    add("implementation", project(":px-module-api"))']
    for m in droid:
        dest = root / m.name
        shutil.copytree(str(m.root / "android"), str(dest), ignore=shutil.ignore_patterns("build", ".gradle")) \
            if (m.root / "android").is_dir() else dest.mkdir(parents=True)
        (dest / "build.gradle.kts").write_text(module_gradle(m))
        includes += ['include(":px-%s")' % m.name, 'project(":px-%s").projectDir = file("pyxpo-gen/modules/%s")' % (m.name, m.name)]
        deps.append('    add("implementation", project(":px-%s"))' % m.name)
    (gen / "modules.settings.gradle.kts").write_text("// Generated by pyxpo.\n" + "\n".join(includes) + "\n")
    (gen / "modules.app.gradle.kts").write_text("// Generated by pyxpo.\ndependencies {\n" + "\n".join(deps) + "\n}\n")
    reg = gen / "runtime" / "java" / "dev" / "pyxpo" / "runtime" / "PxModuleRegistry.kt"
    reg.parent.mkdir(parents=True, exist_ok=True)
    reg.write_text(registry_kotlin(droid))


def check_android_wiring(native: Path) -> None:
    """An ejected project predating autolinking lacks the two lines that pull in module libraries."""
    for rel, line in (("settings.gradle.kts", SETTINGS_LINE), ("app/build.gradle.kts", APP_LINE)):
        f = Path(native) / rel
        if f.is_file() and line not in f.read_text():
            raise BuildError("%s is missing the native-module line; add this to it:\n    %s" % (f, line))
