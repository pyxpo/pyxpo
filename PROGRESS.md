# Pyxpo progress
- Goal: from-scratch Python mobile framework, Expo parity. See DESIGN.md, PLAN.md, RELEASING.md. Tests: `.venv/bin/pytest -q`.
- Env: py3.9; `sed -i ''`; no fg sleep; `pkill -f GradleDaemon` before Android builds. Two iOS sims booted: use UDID D601942E-67CD-4C00-90E0-93886B61B288 (iPhone 17). Android emulator-5554 = AVD pyxpo35 (API 35), start with `-no-audio` (host CoreAudio crash on mic).
- Rules: no Co-Authored-By/Claude attribution in commits/PRs. Outward actions (release, PyPI, tag, push) need user go-ahead.
- Done+committed: runtime, bridge, shells, CLI, hot reload, router, prebuild, distribution, app config + plugins + build_properties, native module system, packages image-manipulator, image-picker, media-library, sharing, storage, file-system, secure-store (e2e both OS). Release 0.1.0a1 on PyPI (8 dists).

## AI Keyboard: pushed; keyboard/speech/translate on PyPI. Open: S23 iOS layout + ML Kit check; pyxpo-llm.

- Oct 29: packages in own repos ../pyxpo-packages/pyxpo-<pkg>; dev_install.sh installs editable.


- Release = bump __version__ + regen editors/vscode/data/pyxpo.json; `pypi` env needs user approval.

## Stability pass (Oct 31, uncommitted): Gradle wedge auto-retry + `pyxpo clean [android|ios]`; include-package hot reload (iOS ok); iOS ships checked-hash .pyc (ios.compile_pyc), cmskite launch 30s->12s first, 8s->6s warm. Suite 603 pass.

## pyxpo-onboarding (Oct 31)
- Core f633c3c pushed: web scroll/snap/clip fixes, onboarding in autolink OFFICIAL. 604 pass.
- cmskite welcome slides shipped (local commit 1252733), e2e on iOS sim pass.
- iOS dev reload fix (Oct 31): R R / Cmd+R caught in PxWindow.sendEvent.

## RTL (Oct 31): cfeac20 pushed. Layout engine mirrors frames, h-scroll anchors right, I18nManager allow/force_rtl (LTR default) on iOS/Android/web. iOS sim verified in Arabic. Android compiles; not yet run on emulator in Arabic. Suite 695 pass.

## Lag audit (Oct 31, local commits f05d616, 39b6da9; cmskite perf commit): debug builds now compile Swift -O / C -Os (iOS xcodebuild cmd + project.yml) and -O2 (Android CMake). Reconciler skips same-element children; memo works with context (readers refreshed). Not yet verified on a phone. Suite 697 pass.


## Nov 1: 53e34b7 (local): return key now fires on_submit_editing; ScrollView keyboard_dismiss_mode on iOS/Android. 699 pass.
- Nov 1: Android keyboard/focus fixes, `Linking.claimed`, TextInput no theme underline (694fee9). a14 on PyPI; a15 tagged (2c72fbf), publish needs user approval. 702 pass.
- Nov 1 cmskite 2fcef9c pushed: post view as article + info sheet; trash rows open sheet (restore/purge). 437 pass, iOS sim checked.
- Nov 1 cmskite AAB 2.0.0 build 10 (e791814 pushed; 3 was used on Play) at ~/Desktop/cmskite-2.0.0-10.aab. AAB = `./gradlew bundleRelease` in android/ with PYXPO_KEYSTORE_PASSWORD env; `pyxpo build android --release` gives APK only.
- Nov 1 6185e34 (local): Android 16+ Back closed app; fix = OnBackInvokedCallback while router/Modal wants Back (`_Back` `can` predicate; root leaves Back to system).
- Nov 1 native nav commit (local): Android Material shared-axis push/pop + predictive-back preview (scale/corners, verified API 37), no own edge drag. iOS spring push/pop, full-screen swipe w/ velocity, shadow (push checked; swipe untested). Not pushed. cmskite needs AAB build 11. Later: UINavigationController, header crossfade.
- Nov 1 8857fe2 (local): core `ImageViewer` (from pyxpo import ImageViewer). Native iOS/Android in runtime (PxModuleHost.all / allModules), web Modal. pyxpo-image-viewer package dropped. Android checked: opens, loads, swipe-down + close button. Not device-checked: double-tap/pinch zoom, swipe between images. cmskite 23a1a9c uses it. Not pushed.
- Nov 1 (local): Android core Image never loaded http(s) URLs: createTempFile("dl") threw "Prefix string too short" (prefix needs 3+ chars). Fixed to "pxdl"; failed loads now retry on re-render. cmskite banner verified on emulator.
