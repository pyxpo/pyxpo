"""Native module autolinking: only the modules an app lists in `[tool.pyxpo] modules` are compiled into it.

A module is an installed pip package with `pyxpo-module.json`, Python code, and optional `ios/*.swift` and
`android/src/main/**` sources, registered under the `pyxpo.modules` entry point group. First-party modules
live in this repo's `packages/` folder and are published as `pyxpo-<name>` (import `pyxpo_<name>`).
Unlisted modules are never copied, so they add no code, permissions or dependencies to the app.
"""
from __future__ import annotations

import ast
import difflib
import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .runtime import BuildError

from ..module_api import NATIVE_CONTRACT

META = "pyxpo-module.json"
SCHEMA_VERSION = 1
NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
CLASS_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
PLIST_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# Swift package fields end up in the generated XcodeGen include, so they are held to plain values.
SPM_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
SPM_URL_RE = re.compile(r"^https://[A-Za-z0-9.-]+(/[A-Za-z0-9._~-]+)+$")
SPM_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
SPM_FILTERS = ("all", "iOS", "macOS")
# `"build": {"hook": "pkg.sub:function"}`: host-side code run while the config loads (see pyxpo.module_hooks).
HOOK_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*:[A-Za-z_][A-Za-z0-9_]*$")
IOS_INCLUDE = "pyxpo-gen/modules.project.yml"
SETTINGS_LINE = 'apply(from = "pyxpo-gen/modules.settings.gradle.kts")'
APP_LINE = 'apply(from = "../pyxpo-gen/modules.app.gradle.kts")'
# First-party modules, published separately; known here only to tell the user which package to install.
OFFICIAL = ("apple-authentication", "application", "audio", "camera", "device", "dot-env", "drawing-canvas", "fetch", "file-system", "google-mobile-ads", "google-sign-in", "haptics", "image-cropper", "image-manipulator", "image-picker", "intl", "keyboard", "localization", "location", "media-library", "mesh-view", "network", "notifications", "onboarding", "pose-detection", "query", "rich-editor", "secure-store", "sharing", "speech", "sqlite", "storage", "svg", "translate", "video", "web-browser", "whiteboard")


def dist_name(name: str) -> str:
    """The pip distribution of a first-party module: `image-picker` -> `pyxpo-image-picker`."""
    return "pyxpo-" + name


def import_name(name: str) -> str:
    """The import package of a first-party module: `image-picker` -> `pyxpo_image_picker`."""
    return "pyxpo_" + name.replace("-", "_")


class Module:
    def __init__(self, root: Path, meta: Dict[str, Any], pkg: str) -> None:
        self.root, self.meta, self.pkg = root, meta, pkg
        self.name: str = meta["name"]
        self.native: str = meta["native"]
        self.ios: Dict[str, Any] = meta.get("ios") or {}
        self.android: Dict[str, Any] = meta.get("android") or {}
        self.web: Dict[str, Any] = meta.get("web") or {}

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
    for key in ("schemaVersion", "nativeContract"):
        v = meta.get(key, 1)
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            raise bad("'%s' must be a positive integer" % key)
    if meta.get("schemaVersion", 1) > SCHEMA_VERSION:
        raise bad("manifest schemaVersion %d is newer than this pyxpo understands (%d): upgrade pyxpo"
                  % (meta["schemaVersion"], SCHEMA_VERSION))
    if meta.get("nativeContract", 1) > NATIVE_CONTRACT:
        raise bad("module needs native contract %d but this pyxpo provides %d: upgrade pyxpo"
                  % (meta["nativeContract"], NATIVE_CONTRACT))
    build = meta.get("build", {})
    if not isinstance(build, dict) or ("hook" in build and not HOOK_RE.match(str(build["hook"]))):
        raise bad("build.hook must look like 'package.module:function'")
    ios, android = meta.get("ios") or {}, meta.get("android") or {}
    if not isinstance(ios, dict) or not isinstance(android, dict):
        raise bad("'ios' and 'android' must be JSON objects")
    deps = android.get("dependencies", [])
    if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
        raise bad("android.dependencies must be a list of strings")
    if not isinstance(android.get("minSdk", 24), int) or isinstance(android.get("minSdk"), bool):
        raise bad("android.minSdk must be an integer")
    cmake = android.get("cmake")
    if cmake is not None:
        path, args = (cmake.get("path"), cmake.get("arguments", [])) if isinstance(cmake, dict) else (None, None)
        if (not isinstance(path, str) or not path.endswith("CMakeLists.txt") or path.startswith("/")
                or ".." in path.split("/") or "\\" in path
                or not isinstance(args, list) or not all(isinstance(x, str) for x in args)):
            raise bad('android.cmake must be {"path": "src/main/cpp/CMakeLists.txt", "arguments": ["-DNAME=value"]}'
                      " with a path inside the module's android folder")
    web = meta.get("web", {})
    if not isinstance(web, dict):
        raise bad("'web' must be a JSON object")
    wpk = web.get("packages", [])
    if not isinstance(wpk, list) or not all(isinstance(p, str) and p.strip() for p in wpk):
        raise bad("web.packages must be a list of package names (installed in the browser with micropip)")
    if not isinstance(ios.get("infoPlist") or {}, dict):
        raise bad("ios.infoPlist must be a JSON object")
    for plat, spec in (("ios", ios), ("android", android)):
        classes = spec.get("classes", [])
        if plat in meta and (not isinstance(classes, list) or not classes
                             or not all(isinstance(c, str) and CLASS_RE.match(c) for c in classes)):
            raise bad("%s.classes must be a non-empty list of class names" % plat)
    if "android" in meta and not re.match(r"^[a-z][a-z0-9_.]*$", str(android.get("namespace", ""))):
        raise bad("android.namespace is required (for example dev.pyxpo.modules.mine)")
    for key, spec in (ios.get("infoPlist") or {}).items():
        # The key becomes an `INFOPLIST_KEY_<key>` xcconfig setting, so anything but an identifier could inject settings.
        if not PLIST_KEY_RE.match(key):
            raise bad("ios.infoPlist key %r must be a plain Info.plist key (letters, digits, underscores)" % key)
        if not isinstance(spec, dict) or "default" not in spec:
            raise bad("ios.infoPlist.%s needs a 'default'" % key)
    pkgs = ios.get("swiftPackages", [])
    if not isinstance(pkgs, list):
        raise bad("ios.swiftPackages must be a list")
    for p in pkgs:
        if not isinstance(p, dict) or not SPM_NAME_RE.match(str(p.get("name", ""))):
            raise bad("ios.swiftPackages entries need a 'name' (letters, digits, dashes, underscores)")
        if not SPM_URL_RE.match(str(p.get("url", ""))):
            raise bad("ios.swiftPackages.%s.url must be an https:// repository URL" % p["name"])
        if not SPM_VERSION_RE.match(str(p.get("version", ""))):
            raise bad("ios.swiftPackages.%s.version must be a version like 12.0.0 (used as the lowest allowed version)" % p["name"])
        prods = p.get("products")
        if not isinstance(prods, list) or not prods or not all(isinstance(x, str) and SPM_NAME_RE.match(x) for x in prods):
            raise bad("ios.swiftPackages.%s.products must be a non-empty list of product names" % p["name"])
        if p.get("platformFilter", "all") not in SPM_FILTERS:
            raise bad("ios.swiftPackages.%s.platformFilter must be one of %s" % (p["name"], ", ".join(SPM_FILTERS)))
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
    """{module name: Module} for every installed module package (`pyxpo.modules` entry points)."""
    found: Dict[str, Module] = {}
    for ep in _entry_points():
        try:
            mod = ep.load()
        except Exception as e:  # noqa: BLE001
            raise BuildError("cannot load native module entry point %r: %s" % (ep.name, e))
        if not getattr(mod, "__file__", None) or Path(mod.__file__).name != "__init__.py":
            raise BuildError("native module entry point %r must point at a regular package" % ep.name)
        m = _load(Path(mod.__file__).resolve().parent, mod.__name__)
        if m is None:
            raise BuildError("module package %s has no %s" % (mod.__name__, META))
        if m.name in found and found[m.name].root.resolve() == m.root:
            continue  # the same distribution listed twice (duplicate sys.path entries)
        if m.name in found:
            raise BuildError("native module name %r is provided twice" % m.name)
        found[m.name] = m
    return found


def find(names: List[str]) -> Dict[str, Module]:
    """The installed modules among `names`, loading only their entry points. Never raises: a broken or missing
    module is left out here and reported by `resolve()` when the build links the app."""
    out: Dict[str, Module] = {}
    for ep in _entry_points():
        if ep.name not in names or ep.name in out:
            continue
        try:
            mod = ep.load()
            f = getattr(mod, "__file__", None)
            m = _load(Path(f).resolve().parent, mod.__name__) if f and Path(f).name == "__init__.py" else None
        except Exception:  # noqa: BLE001
            continue
        if m is not None and m.name == ep.name:
            out[m.name] = m
    return out


def linked_roots(project: Path) -> List[Path]:
    """Package folders of the modules the app links, for dev watchers. Never raises: the build reports errors."""
    from ..config import load_config

    try:
        return [m.root for m in resolve(load_config(Path(project)), Path(project))]
    except Exception:  # noqa: BLE001
        return []


def module_files(roots: List[Path]) -> Dict[str, Tuple[int, int]]:
    """{'<pkg dir>/<rel>': (mtime_ns, size)} for every source file under the given module package folders."""
    out: Dict[str, Tuple[int, int]] = {}
    for root in roots:
        for f in root.rglob("*"):
            if "__pycache__" in f.parts or f.name.startswith(".") or f.suffix == ".pyc":
                continue
            try:
                st = f.stat()
            except OSError:
                continue
            if f.is_file():
                out["%s/%s" % (root.name, f.relative_to(root).as_posix())] = (st.st_mtime_ns, st.st_size)
    return out


def imported_modules(project: Path, known: Dict[str, Module]) -> Dict[str, str]:
    """{module name: 'file:line'} for modules the app's Python code imports, including first-party
    modules whose package is not installed (so the build can say which package to install)."""
    by_pkg = {import_name(n): n for n in OFFICIAL}
    by_pkg.update({m.pkg: m.name for m in known.values()})
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
        if n not in known and n in OFFICIAL:
            raise BuildError("native module %r is listed in [tool.pyxpo] modules but its package is not installed; "
                             "run `pip install %s` in the environment that runs pyxpo" % (n, dist_name(n)))
        if n not in known:
            close = difflib.get_close_matches(n, sorted(set(known) | set(OFFICIAL)), n=3)
            raise BuildError("unknown native module %r in [tool.pyxpo] modules%s (installed: %s). Modules are pip "
                             "packages: install the one that provides %r (first-party ones are named pyxpo-<module>)" % (
                                 n, "; did you mean %s?" % " or ".join(repr(c) for c in close) if close else "",
                                 ", ".join(sorted(known)) or "none", n))
        if known[n] not in out:
            out.append(known[n])
    for name, where in imported_modules(project, known).items():
        if name not in listed:
            raise BuildError("%s imports native module %r but it is not linked: %sadd %r to [tool.pyxpo] modules "
                             "in pyproject.toml" % (where, name, "" if name in known else
                                                    "run `pip install %s` and " % dist_name(name), name))
    return out


def python_files(mods: List[Module]) -> List[Any]:
    """[(source file, path inside the app bundle)] for the linked modules' Python code.

    Module packages live in the host's site-packages, not in the app, so a build copies the linked ones
    next to the `pyxpo` runtime package. Native sources and metadata stay behind."""
    out = []
    for m in mods:
        base = m.pkg.replace(".", "/")
        for f in sorted(m.root.rglob("*.py")):
            rel = f.relative_to(m.root)
            if "__pycache__" in rel.parts or rel.parts[0] in ("ios", "android"):
                continue
            out.append((f, "%s/%s" % (base, rel.as_posix())))
    return out


def link(cfg: Dict[str, Any], project: Path) -> "Linked":
    """What a build links: the resolved modules and their `[tool.pyxpo.module_options.<name>]` tables."""
    opts = cfg.get("module_options") or {}
    if not isinstance(opts, dict):
        raise BuildError("[tool.pyxpo.module_options] must hold one table per module")
    return Linked(resolve(cfg, project), opts)


class Linked:
    def __init__(self, modules: List[Module], options: Dict[str, Any]) -> None:
        self.modules, self.options = modules, options


def info_plist(mods: List[Module], options: Dict[str, Any]) -> Dict[str, str]:
    """Usage-description keys the linked modules need. `options` is `[tool.pyxpo.module_options.<module>]`.
    A module's `infoPlist` table there sets any key directly. Two modules asking for the same key with
    different text is an error unless one of them sets it explicitly. Setting a key to `false` leaves it out (for an app
    that never uses that feature, such as the microphone key `image-picker` adds for video capture)."""
    keys: Dict[str, str] = {}
    owner: Dict[str, str] = {}
    for m in mods:
        opts = (options or {}).get(m.name) or {}
        direct = opts.get("infoPlist") or {}
        for key, spec in (m.ios.get("infoPlist") or {}).items():
            if direct.get(key) is False:
                continue
            explicit = key in direct or spec.get("option", "") in opts
            val = str(direct[key] if key in direct else opts.get(spec.get("option", ""), spec["default"]))
            if key in keys and keys[key] != val and not explicit:
                raise BuildError("modules '%s' and '%s' both set Info.plist key %s with different text; set it in "
                                 "[tool.pyxpo.module_options.%s.infoPlist]" % (owner[key], m.name, key, m.name))
            if key not in keys or explicit:
                keys[key], owner[key] = val, m.name
    return keys


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
    """Copies linked modules' Swift into `pyxpo-gen/runtime/modules/` and writes the registry (Info.plist keys go through Pyxpo.xcconfig)."""
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
    (gen / "runtime" / "PxModuleRegistry.swift").write_text(registry_swift([m for m in mods if m.ios]))
    (gen / "modules.project.yml").write_text(swift_packages_yml(mods))


def swift_packages(mods: List[Module]) -> List[Dict[str, Any]]:
    """Linked modules' Swift packages, one entry per package name. The highest lowest-version wins; products are merged."""
    out: Dict[str, Dict[str, Any]] = {}
    for m in mods:
        for p in m.ios.get("swiftPackages", []):
            cur = out.get(p["name"])
            if cur is None:
                out[p["name"]] = {"name": p["name"], "url": p["url"], "version": p["version"],
                                  "products": list(p["products"]), "platformFilter": p.get("platformFilter", "all"), "owner": m.name}
                continue
            if cur["url"].rstrip("/").lower() != p["url"].rstrip("/").lower():
                raise BuildError("modules %r and %r both use Swift package %r from different URLs (%s, %s)"
                                 % (cur["owner"], m.name, p["name"], cur["url"], p["url"]))
            if tuple(map(int, p["version"].split("."))) > tuple(map(int, cur["version"].split("."))):
                cur["version"] = p["version"]
            cur["products"] += [x for x in p["products"] if x not in cur["products"]]
            if p.get("platformFilter", "all") != cur["platformFilter"]:
                cur["platformFilter"] = "all"  # one module needs it on every platform
    return sorted(out.values(), key=lambda p: p["name"])


def swift_packages_yml(mods: List[Module]) -> str:
    """The XcodeGen include that adds module Swift packages to the PyxpoApp target (project.yml includes it).
    Values are validated plain strings, written JSON-quoted (valid YAML)."""
    pkgs = swift_packages(mods)
    head = "# Generated by pyxpo from linked modules' ios.swiftPackages. Do not edit; project.yml includes it.\n"
    if not pkgs:
        return head + "packages: {}\n"
    lines = [head + "packages:"]
    for p in pkgs:
        lines += ["  %s:" % json.dumps(p["name"]), "    url: %s" % json.dumps(p["url"]), "    from: %s" % json.dumps(p["version"])]
    lines += ["targets:", "  PyxpoApp:", "    dependencies:"]
    for p in pkgs:
        for prod in p["products"]:
            lines += ["      - package: %s" % json.dumps(p["name"]), "        product: %s" % json.dumps(prod)]
            if p["platformFilter"] != "all":
                lines.append("        platformFilter: %s" % p["platformFilter"])
    return "\n".join(lines) + "\n"


def _gradle_str(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$")


def gradle_properties(mods: List[Module]) -> Dict[str, str]:
    """Gradle properties the linked modules need: AndroidX libraries (and Google's libraries built on them, like
    Firebase and ML Kit) refuse to build without `android.useAndroidX`."""
    deps = [d for m in mods if m.android for d in m.android.get("dependencies", [])]
    return {"android.useAndroidX": "true"} if any(d.startswith(ANDROIDX_GROUPS) for d in deps) else {}


ANDROIDX_GROUPS = ("androidx.", "com.google.firebase:", "com.google.android.gms:", "com.google.mlkit:")


# The NDK the app template builds with (templates/android/user/app/build.gradle.kts); modules with C/C++ use it too.
NDK_VERSION = "27.3.13750724"


def _native_gradle(m: Module) -> str:
    """`android.cmake`: the module builds C/C++ with CMake, for the ABIs the app ships (pyxpo.properties `abis`)."""
    cmake = m.android.get("cmake")
    if not cmake:
        return ""
    args = ", ".join('"%s"' % _gradle_str(a) for a in cmake.get("arguments", []))
    return ('    ndkVersion = "%s"\n'
            '    defaultConfig {\n'
            '        ndk { abiFilters += rootProject.file("pyxpo-gen/pyxpo.properties").readLines()'
            '.first { it.startsWith("abis=") }.substringAfter("=").split(",").map { it.trim() } }\n'
            '        externalNativeBuild { cmake { arguments(%s) } }\n'
            '    }\n'
            '    externalNativeBuild { cmake { path = file("%s") } }\n'
            % (NDK_VERSION, args, _gradle_str(cmake["path"])))


def module_gradle(m: Module) -> str:
    deps = "".join('    implementation("%s")\n' % _gradle_str(d) for d in m.android.get("dependencies", []))
    return ('plugins {\n    id("com.android.library")\n    id("org.jetbrains.kotlin.android")\n}\n\n'
            'android {\n    namespace = "%s"\n    compileSdk = 35\n    defaultConfig { minSdk = %d }\n%s'
            '    compileOptions {\n        sourceCompatibility = JavaVersion.VERSION_17\n'
            '        targetCompatibility = JavaVersion.VERSION_17\n    }\n    kotlinOptions { jvmTarget = "17" }\n}\n\n'
            'dependencies {\n    implementation(project(":px-module-api"))\n%s}\n'
            % (m.android["namespace"], int(m.android.get("minSdk", 24)), _native_gradle(m), deps))


def render_android(gen: Path, mods: List[Module]) -> None:
    """Writes one Gradle library per linked module plus the settings/app fragments and the Kotlin registry.
    The Gradle manifest merger then brings each module's permissions and providers into the app."""
    droid = [m for m in mods if m.android]
    root = gen / "modules"
    if root.exists():
        shutil.rmtree(str(root))
    includes = ['include(":px-module-api")', 'project(":px-module-api").projectDir = File(settingsDir, "pyxpo-gen/module-api")']
    deps = ['    add("implementation", project(":px-module-api"))']
    for m in droid:
        dest = root / m.name
        shutil.copytree(str(m.root / "android"), str(dest), ignore=shutil.ignore_patterns("build", ".gradle")) \
            if (m.root / "android").is_dir() else dest.mkdir(parents=True)
        (dest / "build.gradle.kts").write_text(module_gradle(m))
        includes += ['include(":px-%s")' % m.name,
                     'project(":px-%s").projectDir = File(settingsDir, "pyxpo-gen/modules/%s")' % (m.name, m.name)]
        deps.append('    add("implementation", project(":px-%s"))' % m.name)
    (gen / "modules.settings.gradle.kts").write_text("// Generated by pyxpo.\n" + "\n".join(includes) + "\n")
    (gen / "modules.app.gradle.kts").write_text("// Generated by pyxpo.\ndependencies {\n" + "\n".join(deps) + "\n}\n"
                                                 + 'apply(from = "../pyxpo-gen/pyxpo.app.gradle")  // app config: SDK levels, overlay manifests\n')
    reg = gen / "runtime" / "java" / "dev" / "pyxpo" / "runtime" / "PxModuleRegistry.kt"
    reg.parent.mkdir(parents=True, exist_ok=True)
    reg.write_text(registry_kotlin(droid))


def check_android_wiring(native: Path) -> None:
    """An ejected project predating autolinking lacks the two lines that pull in module libraries."""
    for rel, line in (("settings.gradle.kts", SETTINGS_LINE), ("app/build.gradle.kts", APP_LINE)):
        f = Path(native) / rel
        if f.is_file() and line not in f.read_text():
            raise BuildError("%s is missing the native-module line; add this to it:\n    %s" % (f, line))


def check_ios_wiring(native: Path, mods: Optional[List[Module]] = None) -> None:
    """An ejected project predating autolinking sets GENERATE_INFOPLIST_FILE to NO, which drops module Info.plist keys."""
    f = Path(native) / "project.yml"
    if not f.is_file():
        return
    text = f.read_text()
    if mods and swift_packages(mods) and IOS_INCLUDE not in text:
        raise BuildError("%s does not include the module Swift packages (needed by %s); add this at the top level:\n"
                         "include:\n  - path: %s" % (f, ", ".join(sorted({m.name for m in mods if m.ios.get("swiftPackages")})), IOS_INCLUDE))
    if not re.search(r"GENERATE_INFOPLIST_FILE:\s*[\"']?YES", text):
        raise BuildError("%s must set GENERATE_INFOPLIST_FILE: YES (under settings.base) so native-module Info.plist keys are applied" % f)
    if "PYXPO_INFOPLIST" not in text or "deploymentTarget" in text:
        raise BuildError("%s predates the app config. Update it (or delete it and run `pyxpo prebuild ios`): remove "
                         "options.deploymentTarget and settings.base.INFOPLIST_FILE, and add under targets.PyxpoApp:\n"
                         "    settings:\n      base:\n        INFOPLIST_FILE: $(PYXPO_INFOPLIST)\n"
                         "        TARGETED_DEVICE_FAMILY: $(PYXPO_DEVICE_FAMILY)\n"
                         "and exclude Info.plist from the App source: `- path: App` with `excludes: [Info.plist]`" % f)
