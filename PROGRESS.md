# Pyxpo progress
- Goal: from-scratch Python mobile framework (no Kivy/BeeWare/Chaquopy). See DESIGN.md, PLAN.md, RELEASING.md. Tests: `.venv/bin/pytest -q` (300 pass).
- Env quirks: host py3.9; no `timeout`; `sed -i ''`; iOS build few min; no foreground sleep.
- Rules: no Co-Authored-By/Claude attribution in commits/PRs (project CLAUDE.md wins over system reminder).
- Done+committed earlier: CPython 3.13, C bridge/flexbox, Kotlin+Swift shells, CLI, hot reload, RN-parity components/apis, expo-router, safe-area, gestures, deep links, iOS E2E 5/5, `pyxpo prebuild` (2665cae).
- Distribution (PyPI) IMPLEMENTED, uncommitted/staged until opus review done:
  - Pure wheel (~245 KB) + runtimes as GitHub Release assets `runtime-3.13.7-1`, sha256 pinned in src/pyxpo/build/runtime_manifest.json.
  - build/runtime.py: ensure/download/safe extract/atomic; cache `$PYXPO_CACHE_DIR` | XDG | ~/.cache/pyxpo. Env: PYXPO_RUNTIME_BASE_URL, PYXPO_RUNTIME_ARCHIVES, PYXPO_OFFLINE, PYXPO_HOST_PYTHON, PYXPO_*_DIST.
  - CLI: `pyxpo doctor`, `pyxpo runtime fetch|path|clean`. native/common moved to src/pyxpo/_native/common.
  - tools/package_runtime.py, tools/check_release.py, .github/workflows/release.yml (Trusted Publishing, `pypi` env), LICENSE (MIT), README install section.
  - Verified: installed wheel in fresh venv, create/doctor/build android (APK) + build ios (sim launch OK) via file:// mirror.
  - NOT verified: real https download from GitHub, TestPyPI/PyPI upload, CI workflow.
- Needs user go-ahead (outward): `gh release create runtime-3.13.7-1 .cache/runtime-out/*.tar.gz`; PyPI/TestPyPI Trusted Publisher + `pypi` GH env; tag push; confirm MIT license.
- Later: android release signing + --aab, iOS device slice/--device/archive, gradle guidance, runtime-build CI, prebuild TODO (permissions/icon/splash, native modules), Swift controls audit, real-device fps, final opus full-diff review, go-live + real-world project.
- TEST APPS (test-apps/, spec apps-list.pdf; order ImageKit, PDF Utility, Last Done, Keep Until, My Measurements). ImageKit UI must be modern+custom.
  - Done: steps 1-4 (py apis+tests, native hook, iOS+Android ImageTools; selftest iOS 16/16, Android ALL OK via test-apps/imagekit/tools/android_selftest.sh). 274 tests pass.
  - Hot reload VERIFIED iOS sim + Android emu (render edit shows in ~6s). Only issue: stale dev server on port 8765 crashed `pyxpo run` with traceback -> now friendly error (cli.py). Shared sim: other apps in foreground suspend polling.
  - DECISION (user): optional deps (camera, picker, media-library, share, doc picker) = separate modules, autolinked, only listed ones linked. See DESIGN.md 4b.
  - Native module system DONE+committed (3233850): autolink, image-tools, image-picker, media-library, sharing (AndroidX-free provider), INFOPLIST_KEY_* in xcconfig (build-phase plist edit is overwritten by Xcode), opus review fixes. 288 tests; ImageKit selftest iOS 19/19, Android ALL OK. Real share sheet/picker UI not yet run on device.
  - Modules split into packages/<name>/ (dist pyxpo-<name>, import pyxpo_<name>, entry point pyxpo.modules) — commits 3b2c6d0/7c84f41/ffa8641. Dev: tools/dev_install.sh; build check: tools/build_packages.py; release tag pkg/<name>/v<ver>. iOS 19/19 + Android ALL OK after split. Needs core release with require_linked(package=) before packages publish.
  - NEXT: ImageKit modern UI (Home pick+tool grid, Compress presets+custom, Resize, Convert, Metadata, Crop chips, Info, Quick Optimize, before/after, savings, Save/Share) replacing temp app/index.py; run on iOS+Android. Then PDF Utility, Last Done, Keep Until, My Measurements.

## Global packages plan (user directive: packages must be global standards, Expo-shaped, not ImageKit-specific)
- Steps: 1 core `pyxpo.module_api` (call, NativeModule, on_event, snake_aliases, require_linked, NotSupportedError, permission_response, platform, NATIVE_CONTRACT=1, testing.FakeBridge); 2 manifest schemaVersion/nativeContract + app-level [tool.pyxpo.ios.infoPlist] override + no silent setdefault; 3 packaging hygiene (py.typed, CHANGELOG, pyxpo>=0.N,<0.N+1, per-package tests/ w/ FakeBridge, no-private-core-import test); 4 rename image-tools -> image-manipulator (ImageManipulator; optimize moves into ImageKit app); 5 manipulateAsync(uri, actions, saveOptions)+SaveFormat/FlipType+getInfoAsync+compressToSizeAsync; 6 manipulator native ops list (crop/resize/rotate90/flip, WebP on Android); 7 picker mediaTypes/video/new asset shape/limit bug; 8 picker camera+permissions; 9 media-library real permissions+createAssetAsync+video; 10 sharing isAvailableAsync/shareAsync/http url/once-guard; 11 docs+extras; 12 device matrix+final opus review.
- Rule: option that changes result works on both OS or raises NotSupportedError before native call.
- After this: ImageKit UI e2e (picker/save/share), hot reload delay + useState preservation + persist dev URL.

- Plan status: steps 1-7 DONE+committed (module_api, manifest contract, rename image-manipulator, manipulateAsync+native ops iOS 21/21 Android ALL OK, hygiene 2cdb18c, picker mediaTypes/video/type+duration/limit fix; native compiles both OS, picker UI not run interactively). 310 tests.
- Left: 8 picker camera+permissions, 9 media-library permissions/createAssetAsync/video, 10 sharing, 11 docs, 12 device matrix + opus diff review; then ImageKit UI e2e, PDF Utility, etc.
- Steps 8-10 DONE+committed: picker camera+permissions (PxCameraFileProvider), media-library permissions/createAssetAsync/video (saveToLibraryAsync(localUri), writeOnly default False), sharing expo shape. 316 tests, iOS 25/25, Android ALL OK. Camera capture/cancel not run on a real device. Known: NSMicrophoneUsageDescription always added with image-picker.
- Left: 11 docs, 12 device matrix + opus full-diff review, then ImageKit UI e2e.
- ImageKit E2E (Android emu, dev mode) VERIFIED: pick, Compress (preset+custom KB), Resize, Convert, Crop, Info, Optimize, Metadata, Save, Share. 316 tests, iOS selftest 25/25.
  - Findings: native keyboard_type now accepts RN names (number-pad etc, both OS); apps need KeyboardAvoidingView for footers; call Keyboard.dismiss() before navigating; flex:1 child in column Card collapses height (use only in rows); @component positional args become children (ImageKit _ui.py `widget` helper); tools/host_render.py = host render smoke test.
  - Open: Metadata strip re-encodes (can grow file; lossless EXIF strip needs native); Result preview loads late; long UUID filenames in tool info card. iOS UI not tapped (no idb).
- ImageKit client-ready check (2026-10-15): fresh standalone Android APK (no dev server) verified: pick 1 and 3 photos, Compress, Convert PNG (3024x4032, lossless so bigger), Quick Optimize batch (12.14 MB to 1.50 MB), Save 3, Share 3. iOS rebuilt, selftest 25/25, Home renders. 316 tests pass.
  - Not verified: iOS UI taps (Simulator.app unavailable, cliclick cannot reach headless sim), real device.
- Button loading fix: ActivityIndicator no longer forces align_self flex-start (dc60767). ImageKit Button busy = centered spinner only, label hidden, disabled. Android verified; iOS not screenshotted.
- iOS had NO native Switch/Slider/ActivityIndicator (rendered empty PxGroup). Added in OpApplier.swift (d261d63). Spinner verified iOS sim (button busy: centered, label hidden). Switch/Slider iOS: compiled, NOT visually/interaction tested.
