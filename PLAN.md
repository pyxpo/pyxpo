# Pyxpo implementation plan

See DESIGN.md. Each step can be done on its own, and each one ends with passing tests or a working demo. Core code must stay compatible with Python 3.9 (`from __future__ import annotations`, no `match`).

## Milestone 1: pure-Python core (dev machine only)
1. **Package skeleton.**
   - Files: `pyproject.toml` (name `pyxpo`, script `pyxpo = pyxpo.cli:main`, extra `dev` = pytest), `src/pyxpo/__init__.py`, `tests/__init__.py`, `.gitignore`, `README.md`.
   - Done when `pip install -e .[dev]` and `pytest` both run.
2. **Elements.**
   - Files: `src/pyxpo/element.py`, `tests/test_element.py`.
   - `Element(type, props, children, key)`. Host primitives are `View`, `Text`, `Button`, `Image`, `TextInput`, `ScrollView` (positional children, keyword props). Nested lists and `None` children are flattened.
3. **Components and hooks.**
   - Files: `src/pyxpo/component.py`, `src/pyxpo/hooks.py`, `tests/test_hooks.py`.
   - Write the `@component` decorator. Track the current fiber with a module-level stack. The hooks are `use_state` (value or updater fn), `use_ref`, `use_memo`, `use_callback`, `use_effect` (deps, cleanup), and `create_context`/`use_context`.
   - Calling a hook outside render, or in a changing order, raises an error.
4. **Ops protocol.**
   - Files: `src/pyxpo/ops.py`, `tests/test_ops.py`.
   - Write dataclasses for create/update/insert/remove/delete and `to_json`/`from_json`. Callable props become `True`, and a handler registry maps `(node_id, event)` to fn.
5. **Reconciler.**
   - Files: `src/pyxpo/reconciler.py`, `tests/test_reconciler.py`.
   - Fibers mount and update. Matching is by `(type, key)`, then index. Props are diffed into `update`, and `removed` lists dropped keys. Keyed moves become `remove`+`insert`. Unmount runs effect cleanups and emits `delete`. Ids are ints, and root id = 1.
   - Output is one ops list per commit.
6. **Scheduler and app loop.**
   - Files: `src/pyxpo/scheduler.py`, `src/pyxpo/app.py`, `tests/test_scheduler.py`.
   - asyncio-based. setState marks the fiber dirty and schedules one flush per tick. Effects run after the commit. `dispatch_event(json)` calls the handler.
   - `run_app(Root, channel)` and `use_async(coro_fn, deps)` (heavy work goes to `asyncio.to_thread`).
7. **Channel and MockRenderer.**
   - Files: `src/pyxpo/channel.py` (`Channel` ABC, `LocalChannel`), `src/pyxpo/renderers/mock.py`, `tests/test_mock_renderer.py`.
   - The mock applies ops to an in-memory tree and can `press(id)`.
   - Counter end-to-end test: render, press, check the text.
8. **Desktop preview (optional).**
   - Files: `src/pyxpo/renderers/tk.py`.
   - Maps primitives to tkinter widgets with a simple pack layout, and turns Tk callbacks into event JSON. Smoke test is skipped when there is no display.
9. **CLI skeleton.**
   - Files: `src/pyxpo/cli.py`, `src/pyxpo/config.py` (reads `[tool.pyxpo]` using `tomli` on 3.9 and `tomllib` on 3.11+), `src/pyxpo/templates/app/{pyproject.toml.tmpl,app/main.py.tmpl}`, `tests/test_cli.py`.
   - Commands are `create`, `run desktop`, and `doctor` (prints which toolchains were found). `run android|ios` and `build` exit with "not yet implemented".
10. **`add-lib` wheel check.**
    - Files: `src/pyxpo/libs.py`, `src/pyxpo/platforms.py` (target → pip platform tags), `tests/test_libs.py` (subprocess mocked).
    - Runs `pip download --only-binary=:all: --no-deps --platform <tag> --python-version 3.13 -d tmp` for each target, prints a table, and updates `requires`. It has a special-case message for `tensorflow`/`torch`.
11. **Example and docs.**
    - Files: `examples/counter/`, `examples/todo/` (keyed lists, TextInput), README quickstart.
    - Milestone 1 is done when `pyxpo create demo && cd demo && pyxpo run desktop` works.

## Milestone 2: Android (own shell, own CPython build)
12. **CPython cross-build script.**
    - Files: `native/android/build_cpython.py`.
    - Uses CPython 3.13 source with its in-tree `Android/` build support and the NDK. Outputs `dist/android/<abi>/{libpython3.13.so, lib/python3.13/, lib-dynload}` for arm64-v8a and x86_64, with a hash manifest.
13. **C bridge module.**
    - Files: `native/common/pyxpo_bridge.c`, `native/common/pyxpo_bridge.h`.
    - Builtin module `_pyxpo_bridge` with `post(str)` and `set_event_handler(fn)`. A platform callback pointer is set by the host. Native-to-Python calls use `PyGILState_Ensure`.
14. **Python-side native channel.**
    - Files: `src/pyxpo/channel_native.py`.
    - `NativeChannel` wraps `_pyxpo_bridge`, and the event queue feeds the asyncio loop with `loop.call_soon_threadsafe`.
15. **Android shell template.**
    - Files: `src/pyxpo/templates/android/` (Gradle project, `MainActivity.kt`, `PyxpoRuntime.kt`, `cpp/pyxpo_jni.c`, `cpp/CMakeLists.txt`).
    - Extracts assets to `filesDir/pyxpo/<hash>`, starts the Python thread, and calls `PyConfig`/`Py_InitializeFromConfig`, then `app.main`.
    - **Risk to verify:** `dlopen` of extracted `.so` files works on API 24 and on the latest API.
16. **Kotlin op applier.**
    - Files: `templates/android/.../OpApplier.kt`, `PyxpoLayout.kt`.
    - Keeps a map of id → View. Runs on `Handler(mainLooper)`. Maps primitives to native widgets, applies the flex subset, and wires events back to the bridge.
17. **`pyxpo build android` / `run android`.**
    - Files: `src/pyxpo/build/android.py`.
    - Renders the template, pip-installs per ABI with `--platform android_24_<abi>`, compiles to `.pyc`, zips the assets, then runs `gradlew assembleDebug` and `adb install`.
    - Demo: Counter on an emulator, then a numpy example.

## Milestone 3: iOS
18. **Python.xcframework build.**
    - Files: `native/ios/build_cpython.py`.
    - Uses CPython in-tree iOS support. Builds device arm64 plus simulator arm64 and x86_64, and outputs the xcframework and stdlib.
19. **iOS shell template.**
    - Files: `src/pyxpo/templates/ios/` (XcodeGen `project.yml`, `AppDelegate.swift`, `PyxpoRuntime.m`, `OpApplier.swift`, `PyxpoLayout.swift`, bridging header). The shell reuses `pyxpo_bridge.c`.
20. **iOS packaging.**
    - Files: `src/pyxpo/build/ios.py`, `native/ios/wrap_frameworks.py`.
    - Pip-installs per SDK and turns `.so` files into `.framework`s plus `.fwork` stubs. Adds a codesign build phase, then `xcodebuild` and `simctl install`/launch.

## Milestone 4: ecosystem
21. **`pyxpo-wheels` CI.** Files: `wheels/recipes/*.toml`, `.github/workflows/wheels.yml`. Uses cibuildwheel for iOS and Android to build numpy, Pillow, and ai-edge-litert.
22. **Dev server and hot reload** for debug builds only. Files: `src/pyxpo/devserver.py`, plus a websocket client in each shell.
23. **More components and layout:** FlatList, Switch, navigation, and the full flexbox spec.
