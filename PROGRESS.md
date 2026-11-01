# Pyxpo progress
- Goal: from-scratch Python mobile framework, Expo parity. See DESIGN.md, PLAN.md, RELEASING.md. Tests: `.venv/bin/pytest -q`.
- Env: py3.9; `sed -i ''`; no fg sleep; `pkill -f GradleDaemon` before Android builds. Two iOS sims booted: use UDID D601942E-67CD-4C00-90E0-93886B61B288 (iPhone 17). Android emulator-5554 = AVD pyxpo35 (API 35), start with `-no-audio` (host CoreAudio crash on mic).
- Rules: no Co-Authored-By/Claude attribution in commits/PRs. Standing go-ahead: after verified core/package changes, push + tag + PyPI release (approve `pypi` env via gh api pending_deployments). App pushes/store builds still ask.
- Done+committed: runtime, bridge, shells, CLI, hot reload, router, prebuild, distribution, app config + plugins + build_properties, native module system, packages image-manipulator, image-picker, media-library, sharing, storage, file-system, secure-store (e2e both OS). Release 0.1.0a1 on PyPI (8 dists).

## AI Keyboard: pushed; on PyPI. Open: S23 iOS layout, ML Kit, pyxpo-llm.
- Packages: ../pyxpo-packages/pyxpo-<pkg>; dev_install.sh.

## Stability pass (Oct 31, uncommitted): Gradle wedge auto-retry + `pyxpo clean [android|ios]`; include-package hot reload (iOS ok); iOS ships checked-hash .pyc (ios.compile_pyc), cmskite launch 30s->12s first, 8s->6s warm. Suite 603 pass.

## pyxpo-onboarding (Oct 31)
- Core f633c3c pushed: web scroll/snap/clip fixes, onboarding in autolink OFFICIAL. 604 pass.
- cmskite welcome slides shipped (local commit 1252733), e2e on iOS sim pass.
- iOS dev reload fix (Oct 31): R R / Cmd+R caught in PxWindow.sendEvent.

## RTL (Oct 31): cfeac20 pushed. Layout engine mirrors frames, h-scroll anchors right, I18nManager allow/force_rtl (LTR default) on iOS/Android/web. iOS sim verified in Arabic. Android compiles; not yet run on emulator in Arabic. Suite 695 pass.

## Lag audit (Oct 31): debug builds Swift -O / C -Os / Android -O2; reconciler skips same-element children. Not phone-verified.
## Nov 1: return key fires on_submit_editing; ScrollView keyboard_dismiss_mode.
- Nov 1: Android keyboard/focus fixes, `Linking.claimed`, TextInput no underline (a14/a15).
- Nov 1 cmskite 2fcef9c pushed: article view, info/trash sheets.
- Nov 1 cmskite AAB 2.0.0 build 10 (e791814 pushed; 3 was used on Play) at ~/Desktop/cmskite-2.0.0-10.aab. AAB = `./gradlew bundleRelease` in android/ with PYXPO_KEYSTORE_PASSWORD env; `pyxpo build android --release` gives APK only.
- Nov 1 6185e34 (local): Android 16+ Back closed app; fix = OnBackInvokedCallback while router/Modal wants Back (`_Back` `can` predicate; root leaves Back to system).
- Nov 1 native nav commit (local): Android Material shared-axis push/pop + predictive-back preview (scale/corners, verified API 37), no own edge drag. iOS spring push/pop, full-screen swipe w/ velocity, shadow (push checked; swipe untested). Not pushed. cmskite needs AAB build 11. Later: UINavigationController, header crossfade.
- Nov 1 8857fe2 (local): core `ImageViewer` (from pyxpo import ImageViewer). Native iOS/Android in runtime (PxModuleHost.all / allModules), web Modal. pyxpo-image-viewer package dropped. Android checked: opens, loads, swipe-down + close button. Not device-checked: double-tap/pinch zoom, swipe between images. cmskite 23a1a9c uses it. Not pushed.
- Nov 1 (local): Android Image http(s) fix (createTempFile prefix "dl" too short). Android 12+ splash icon = inset drawable (240dp canvas x1.2), matches overlay size, no crop; verified on emulator. 710 pass.
- Nov 1: released core 0.1.0a16; file-system, image-picker, media-library, sharing, sqlite, apple-authentication, google-sign-in 0.1.0a2 on PyPI.
- Nov 2: released core 0.1.0a18 (bench gaps): FlatList measured windowing, memo(fn), Animated.ValueXY, PanResponder gates/snake_case, Image relative paths. 715 pass. Bench notes: ../pyxpo-apps/bench/.
- Nov 2: a19: Android implicit shell keeps Gradle state (Python-only rebuild 389s -> 31s); stdlib.zip shared, only lib-dynload/sysconfig per ABI (bench APK 26.2 -> 20.7 MB). 717 pass.
