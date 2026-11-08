# Pyxpo progress
- Goal: from-scratch Python mobile framework, Expo parity. See DESIGN.md, PLAN.md, RELEASING.md. Tests: `.venv/bin/pytest -q`.
- Env: py3.9; `sed -i ''`; no fg sleep; `pkill -f GradleDaemon` before Android builds. iOS sim UDID D601942E-67CD-4C00-90E0-93886B61B288 (iPhone 17). Android emulator-5554, start with `-no-audio`.
- Rules: no Co-Authored-By/Claude attribution in commits/PRs. Standing go-ahead: after verified core/package changes, push + tag + PyPI release (approve `pypi` env via gh api pending_deployments). App pushes/store builds still ask.
- Done+committed: runtime, bridge, shells, CLI, hot reload, router, prebuild, distribution, app config + plugins + build_properties, native module system, packages image-manipulator, image-picker, media-library, sharing, storage, file-system, secure-store (e2e both OS). Release 0.1.0a1 on PyPI (8 dists).

- Done earlier: AI Keyboard, onboarding, RTL (cfeac20), lag audit, keyboard fixes.
- Packages: ../pyxpo-packages/pyxpo-<pkg>; dev_install.sh.

## Stability pass (Oct 31, uncommitted): Gradle wedge auto-retry + `pyxpo clean [android|ios]`; include-package hot reload (iOS ok); iOS ships checked-hash .pyc (ios.compile_pyc), cmskite launch 30s->12s first, 8s->6s warm. Suite 603 pass.



## Nov 1: return key fires on_submit_editing; ScrollView keyboard_dismiss_mode.
- Nov 1 cmskite 2fcef9c pushed: article view, info/trash sheets.
- Nov 1 cmskite AAB 2.0.0 build 10 (e791814 pushed; 3 was used on Play) at ~/Desktop/cmskite-2.0.0-10.aab. AAB = `./gradlew bundleRelease` in android/ with PYXPO_KEYSTORE_PASSWORD env; `pyxpo build android --release` gives APK only.
- Nov 1 6185e34 (local): Android 16+ Back closed app; fix = OnBackInvokedCallback while router/Modal wants Back (`_Back` `can` predicate; root leaves Back to system).
- Nov 1 native nav commit (local): Android Material shared-axis push/pop + predictive-back preview (scale/corners, verified API 37), no own edge drag. iOS spring…
- Nov 1 8857fe2 (local): core `ImageViewer` (from pyxpo import ImageViewer). Native iOS/Android in runtime (PxModuleHost.all / allModules), web Modal. pyxpo-image-viewer…
- Nov 1 (local): Android Image http(s) fix (createTempFile prefix "dl" too short). Android 12+ splash icon = inset drawable (240dp canvas x1.2), matches overlay size, no crop; verified on emulator. 710 pass.
- Nov 1: released core 0.1.0a16; file-system, image-picker, media-library, sharing, sqlite, apple-authentication, google-sign-in 0.1.0a2 on PyPI.
- Nov 2 bench gap fixes, all on PyPI (notes: ../pyxpo-apps/bench/notes/gaps.md): a18 FlatList measured windowing, memo(fn), ValueXY, PanResponder gates; a19 Gradle state…
- Android emulator: AVD Pixel_10 (pyxpo35 gone).
- Nov 2 store-ready pass released core 0.1.0a23 (b0fd2b8): build_properties like expo-build-properties via pyxpo-gen/pyxpo.app.gradle, minify default ON, generated R8…
- Next: cmskite gets R8 + symbols on next prebuild; suggest target_sdk 36; AAB needs ask.
- Nov 2 a24: Android grid Image decodes at frame size (heap 161->43 MB).
- Nov 2 a25 (a24 tag failed CI, stale vscode data): iOS Image ImageIO decode at view size. a26: iOS app slimmer: stdlib drops .opt-1/.opt-2 pyc, release ships sourceless .pyc, skips pydoc_data/_pyrepl/CPython test extensions; ios_wrap prunes stale extension frameworks. Bench app 69.5 -> 35 MB (Expo 41). 731 pass.
- Nov 8: web build writes favicon/apple-touch/192/512 icons + manifest.webmanifest from app icon, links in index.html {{HEAD}} (build/web.py). Uncommitted. 2 pre-existing fails: autolink/packages see extra filter-camera, whiteboard dirs.
