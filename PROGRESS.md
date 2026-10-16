# Pyxpo progress
- Goal: from-scratch Python mobile framework, Expo parity. See DESIGN.md, PLAN.md, RELEASING.md. Tests: `.venv/bin/pytest -q`.
- Env quirks: host py3.9 (package code must run on 3.9); no `timeout`; `sed -i ''`; no foreground sleep; `pkill -f GradleDaemon` before Android builds. Two iOS sims booted: use UDID D601942E-67CD-4C00-90E0-93886B61B288 (iPhone 17). Android emulator-5554 is now AVD Pixel_10 (API 37; pyxpo35 gone). If user RUNNING_LOCKED: `adb shell locksettings verify --old 1111` (old AVD had test PIN).
- Rules: no Co-Authored-By/Claude attribution in commits/PRs. Outward actions (release, PyPI, tag, push) need user go-ahead.
- Done+committed: runtime, bridge, shells, CLI, hot reload, router, prebuild, distribution, app config + plugins + build_properties, native module system, packages image-manipulator, image-picker, media-library, sharing, storage, file-system, secure-store (e2e both OS). Release 0.1.0a1 on PyPI (8 dists).
- 0.1.0a2 core + 11 Tier 1 packages (0.1.0a1) on PyPI, Oct 16. All pushed. wheelhouse/ gitignored (tracked a1 wheel broke CI).

## Tier 1 packages (all built, Oct 16) — committed + pushed
- Order: haptics, device, application, localization, network, fetch, sqlite, web-browser, location, notifications, camera (camera needs core module-view support).
- Names follow Expo: pyxpo-<expo name> (expo-network = network state; fetch = HTTP like expo/fetch).
- Core change (uncommitted): module constants. NATIVE_CONTRACT 2. iOS `static var constants` on PxModule (default [:]), Android `open fun constants(context)`. Sent once in startup env as `module_constants`; `pyxpo.module_api.constants(native)`; FakeBridge(constants=...). Packages using constants set nativeContract 2.
- Each package: packages/<name> (py + ios swift + android kt), tests/test_pkg_<name>.py (FakeBridge), add name to autolink.OFFICIAL, e2e via test-apps/tier1kit selftest (pattern: test-apps/storagekit tools/*_selftest.sh).
- Status: haptics, device, application, localization, network, fetch, sqlite, web-browser, location: done, unit + e2e iOS/Android (details in each README). fetch test server tools/fetch_server.py :8765. web-browser Android 15+: BAL + freezer, test closes tab via host `tabback`.
  - notifications: done, unit + e2e iOS/Android (local only; push raises NotSupportedError). Android AlarmManager + boot receiver + trampoline activity for taps; iOS UNUserNotificationCenter delegate. Harness: iOS simctl push, bg; Android tapnotif/bgnotif (shade + uiautomator, retries).
  - camera: py + ios + android written, 14 unit tests. e2e pass both OS (iOS sim: no camera, mount_error; scan_from_url via Core Image QR on sim, Vision on device. Android: photo/video/front/scan). Full tier1kit regression ALL OK iOS + Android. Fixture tools/fixtures/qr.png; tier1kit `_boot.show(el)` mounts test views.
- Core change (uncommitted): native module views. Python `native_view(Type)`, `view_tag(ref)`; iOS PxViewModule/PxNativeView + ctx.view(tag); Android PxModule.viewTypes/makeView, PxNativeView, PxViewFrame. emit("x") calls prop on_x.
- Core change (uncommitted): PxAppLaunchObserver (iOS) — PyxpoRuntime.m +load observes didFinishLaunching, calls observers (notifications delegate installs at launch).
- Core change (uncommitted): native AppState events. iOS OpApplier observers (active/inactive/background), Android MainActivity onResume/onPause -> `app_state` event. Before this AppState was always "active".
- Core change (uncommitted): autolink gradle_properties (androidx dep adds android.useAndroidX=true).
- tests/test_rn_style_example.py fixture now cleans `app` modules before too (test_cli leaked them; failed on HEAD).
- tier1kit harness: tools/ios_selftest.sh|android_selftest.sh [sections]; NOBUILD=1 (Python changes need rebuild); host actions via cache/t1_req -> t1_ack. Android web-browser prep sets Chrome flags (skip first-run). Android python stdout: logcat tag python.stdout.
