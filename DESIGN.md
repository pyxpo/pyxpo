# Pyxpo: design (working name)

A from-scratch framework: a React-Native-style Python app runs on real CPython with native widgets. C-extension libraries (numpy, Pillow, TFLite) work when a mobile wheel exists.

## 1. Runtime: our own embedded CPython
No Chaquopy, Briefcase, python-for-android, Kivy, Flet, or Pyodide (references only). Raw ingredients: **CPython 3.13+ source** with in-tree Android/iOS build support (PEP 738/730), **Android NDK**, Xcode, **cibuildwheel** wheel tags.

**One Python version per Pyxpo release** (default 3.13) on all targets.

**Android loader** (`shell-android/`)
- `libpython3.13.so` cross-built for `arm64-v8a`/`x86_64` in `jniLibs/<abi>`.
- stdlib, `lib-dynload`, site-packages ship as a versioned asset, extracted to `filesDir/pyxpo/<hash>/` on first launch or hash change.
- `pyxpo_jni.c` runs `Py_InitializeFromConfig` (home/path = extracted dirs) on a `PyxpoPython` thread, then `pyxpo.router.entry` (file-based routing over `app/`; legacy `app/main.py` still runs).

**iOS loader** (`shell-ios/`)
- `Python.xcframework` (device arm64; simulator arm64+x86_64) built from CPython source; `PyxpoRuntime.m` sets `PyConfig` from the bundle.
- Each `.so` wrapped as a signed `.framework` with a `.fwork` stub, resolved by CPython's `AppleFrameworkLoader`.

**Honest limits**
- **"Every library works" is false.** Pure-Python libraries always work. A native library needs a wheel for `android_24_<abi>` / `ios_13_0_arm64_iphoneos` / `..._iphonesimulator`. PyPI coverage is still small, so Pyxpo keeps **its own wheel index** (`pyxpo-wheels`), built with cibuildwheel's iOS and Android support. The first set is numpy, Pillow, and ai-edge-litert/TFLite. Porting libraries is the main ongoing cost.
- **Full TensorFlow/PyTorch will not run** (too big, no mobile builds). `add-lib tensorflow` offers TFLite or ONNX Runtime mobile.
- **iOS App Store:** no downloaded code; every `.so` in a signed framework; no `fork`/`subprocess`/JIT. Bundled Python is allowed; hot reload is debug-only.
- **Android:** extracted `.so` files stay in the app-private dir (`dlopen` only, no exec); verify on API 24 and latest (PLAN step 15).
- **Size:** base app ~15-25 MB, numpy +~10 MB. Releases ship `.pyc` only.

## 2. UI architecture (React Native model)
```
[Python thread] components -> hooks -> reconciler -> ops batch (JSON)
      | one crossing per commit, via the C bridge module `_pyxpo_bridge`
[UI thread] Kotlin/Swift op applier -> android.view.View / UIView
      | events (JSON) go into a thread-safe queue that the Python asyncio loop reads
```
**Bridge choice: batched JSON messages, not per-widget JNI/ObjC calls.**
- One crossing per commit; Python never touches the UI thread.
- The same protocol drives the mock renderer, desktop preview, both phones, and dev-server reload.
- `_pyxpo_bridge` (~100 lines C): `post(str)` sends ops; `set_event_handler(fn)` receives events (called under `PyGILState_Ensure`).
- Large data passes as file paths/handles. msgpack can replace JSON later behind `Channel`.

**Ops**
```
{"op":"create","id":5,"type":"Text","props":{"text":"Hi"}}
{"op":"update","id":5,"props":{"text":"Hey"},"removed":["style"]}
{"op":"insert","parent":1,"id":5,"index":0}   {"op":"remove","parent":1,"id":5}
{"op":"delete","id":5}        native -> py: {"event":"press","id":7,"payload":{}}
```
Callables never cross the bridge. `on_press=fn` is sent as `"on_press": true`, and the handler is kept in Python, keyed by `(id, "press")`.

**Component API**
```python
from pyxpo import component, use_state, use_effect, View, Text, Button, run_app

@component
def Counter(start: int = 0):
    count, set_count = use_state(start)
    use_effect(lambda: print("count", count), [count])
    return View(
        Text(f"Count: {count}", style={"font_size": 24}),
        Button("Add", on_press=lambda: set_count(lambda c: c + 1)),
        style={"padding": 16, "gap": 8},
    )

run_app(Counter)
```
- Children are positional and props are keyword arguments. `key=` is used for lists.
- Hooks: `use_state`, `use_effect`, `use_ref`, `use_memo`, `use_callback`, `use_context`.
- Reconciler: it matches by `(type, key)` and diffs props. setState calls are batched and flushed once per loop tick.
- Host primitives in v1: View, Text, Button, Image, TextInput, ScrollView.
- Layout: our own flexbox subset (column/row, padding, gap, flex), computed natively.

## 3. CLI and template
- `pyxpo create <name>`
- `pyxpo run [desktop|android|ios]`
- `pyxpo build android|ios [--release]`
- `pyxpo add-lib <pkg>`: checks for a wheel per target with `pip download --only-binary=:all: --platform <tag> --index-url pyxpo-wheels --extra-index-url pypi`, then writes the library into `pyproject.toml`.
- `pyxpo doctor`

```
myapp/
  pyproject.toml   # [tool.pyxpo] name, bundle_id, targets, requires
  app/_layout.py, app/index.py, ...   # file-based routes (pyxpo.router)
  assets/
  build/           # generated android/ + ios/ shells from Pyxpo templates (gitignored)
```

## 4. Dependency bundling
`pyxpo build` runs `pip install --target build/site/<platform>-<abi> --platform <tag> --only-binary=:all:` for every ABI. Then:
- **Android:** each ABI's site dir is zipped into an asset that is selected at runtime by `Build.SUPPORTED_ABIS`.
- **iOS:** device and simulator site dirs are kept separate. An Xcode build phase picks one by SDK, then wraps and signs the `.so` files.
- `.py` files are compiled to `.pyc` with the target interpreter's magic number.
- When a wheel is missing, the tool prints a cibuildwheel recipe hint.

## 4b. Optional native modules (autolinking)

Anything beyond the core (image tools, picker, media library, sharing, later camera and documents) is a separate module, as in Expo.
An app lists what it uses in `[tool.pyxpo] modules = [...]`; only those are compiled in (Swift copied into the Xcode project, one Gradle
library per module on Android). Unlisted modules add no code, no permissions and no Info.plist keys.

Every module, first-party included, is its own pip package, released separately from core (like `expo-image-picker`). First-party
ones live in `packages/<name>/` in this repo: distribution `pyxpo-<name>`, import package `pyxpo_<name_with_underscores>`, autolink
name `<name>` (the string apps put in `modules`). The import package holds the Python API plus its native side as package data:
`pyxpo-module.json` (bridge name, Swift and Kotlin classes, Android namespace and dependencies, usage-description keys), `ios/*.swift`
and `android/src/main/**`. Each package registers itself under the `pyxpo.modules` entry point group (`image-picker = "pyxpo_image_picker"`),
which is the only way `pyxpo build` discovers modules; third-party modules work exactly the same way.

At build time autolinking (`pyxpo/build/autolink.py`) resolves the listed names against the installed entry points, copies the
native sources into the generated project, and copies the linked packages' Python files into the app next to the `pyxpo` runtime
package (they live in the host's site-packages, so nothing else would bundle them). A module that is listed but not installed fails
the build with `pip install pyxpo-<name>`; importing `pyxpo_<name>` without listing it fails the build with a hint; calling a module
whose native side is not linked raises `ModuleNotLinkedError` naming the pip package and the `modules` entry. Core keeps only the
module host helpers (`pyxpo.modules`: `require_linked`, `ModuleNotLinkedError`, `on_event`).

Monorepo development: `tools/dev_install.sh` installs core and every package in `packages/` editable into `.venv`.
`python tools/build_packages.py` builds and checks every package's wheel and sdist (native files and entry point present);
`python tools/module_size_report.py` prints each first-party module's source footprint.

## 5. Milestones
1. **Pure-Python core**, no mobile toolchains: elements, hooks, reconciler, scheduler, ops, `MockRenderer`, optional Tk preview, CLI skeleton (`create`, `run desktop`, `add-lib` check), pytest. Python 3.9+.
2. **CPython cross-build for Android** plus the Kotlin shell, JNI loader, bridge, and View applier. Counter runs on an emulator, then numpy runs.
3. **iOS:** Python.xcframework, the Swift shell, the bridge, the UIKit applier, and `.so` framework wrapping.
4. The `pyxpo-wheels` index, the dev server with hot reload, and more components.
