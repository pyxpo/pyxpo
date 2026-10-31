# Pyxpo progress
- Goal: from-scratch Python mobile framework, Expo parity. See DESIGN.md, PLAN.md, RELEASING.md. Tests: `.venv/bin/pytest -q`.
- Env quirks: host py3.9; no `timeout`; `sed -i ''`; no foreground sleep; `pkill -f GradleDaemon` before Android builds. Two iOS sims booted: use UDID D601942E-67CD-4C00-90E0-93886B61B288 (iPhone 17). Android emulator-5554 = AVD pyxpo35 (API 35), start with `-no-audio` (host CoreAudio crash on mic).
- Rules: no Co-Authored-By/Claude attribution in commits/PRs. Outward actions (release, PyPI, tag, push) need user go-ahead.
- Done+committed: runtime, bridge, shells, CLI, hot reload, router, prebuild, distribution, app config + plugins + build_properties, native module system, packages image-manipulator, image-picker, media-library, sharing, storage, file-system, secure-store (e2e both OS). Release 0.1.0a1 on PyPI (8 dists).
- Oct 16-19: 0.1.0a2-a4, 11 Tier 1 pkgs, notifications (FCM/APNs), dot-env, google-mobile-ads on PyPI.

## Oct 17-29: VS Code ext, desktop/web, Catalyst, pyxpo-video pushed. Gradle hang: `JAVA_TOOL_OPTIONS=-Djava.net.preferIPv6Addresses=true`.
## AI Keyboard: pushed; keyboard/speech/translate on PyPI. Open: S23 iOS layout + ML Kit check; pyxpo-llm.

## Package repos split (Oct 29)
- packages/ removed from monorepo; clones in ../pyxpo-packages/pyxpo-<pkg> (PYXPO_PACKAGES overrides).
- tools/build_packages.py --path/--tag, dev_install.sh clones missing + `--no-deps -e`. Core suite 564 pass; all 29 package suites pass.
- Oct 29 all repos pushed; trusted publishers, rulesets.

- Core a9-a11 on PyPI (Oct 29-30).


## Oct 30 release batch
- On PyPI: pyxpo-image-manipulator 0.1.0a2, pyxpo-image-cropper 0.1.0a1 (new repo pyxpo/pyxpo-image-cropper, settings+ruleset+pypi env+pvr done).
- Core 0.1.0a12 on PyPI. `pypi` env in core repo has required reviewer: user approves each release.

## 6 new package repos (Oct 30): all on PyPI 0.1.0a1
- rich-editor,query,intl,svg,google-sign-in,apple-authentication: repos fully set up.
- Core 0.1.0a13 on PyPI (Oct 30). Release = bump __version__ + regen editors/vscode/data/pyxpo.json.
- fetch/secure-store/storage 0.1.0a2 on PyPI (Oct 30, floor pyxpo>=0.1.0a4).
- Next: README screenshots (rich-editor + 4 others); device tests iOS sim/emulator/S23.

## Stability pass (Oct 31, uncommitted): Gradle wedge auto-retry + `pyxpo clean [android|ios]`; include-package hot reload (iOS ok); iOS ships checked-hash .pyc (ios.compile_pyc), cmskite launch 30s->12s first, 8s->6s warm. Suite 603 pass.

## pyxpo-onboarding (Oct 31)
- pyxpo/pyxpo-onboarding on GitHub (Oct 31), CI green. 0.1.0a1 on PyPI (tag v0.1.0a1).
- Core f633c3c pushed: web scroll/snap/clip fixes, onboarding in autolink OFFICIAL. 604 pass.
- cmskite welcome slides shipped (local commit 1252733), e2e on iOS sim pass.
- e12cc3d (local): archive/key/monitor/puzzle/sparkles icons + path test. 689 pass.
- iOS dev reload fix (Oct 31): R R / Cmd+R caught in PxWindow.sendEvent.

## RTL (Oct 31): cfeac20 pushed. Layout engine mirrors frames, h-scroll anchors right, I18nManager allow/force_rtl (LTR default) on iOS/Android/web. iOS sim verified in Arabic. Android compiles; not yet run on emulator in Arabic. Suite 695 pass.

## Lag audit (Oct 31, local commits f05d616, 39b6da9; cmskite perf commit): debug builds now compile Swift -O / C -Os (iOS xcodebuild cmd + project.yml) and -O2 (Android CMake). Reconciler skips same-element children; memo works with context (readers refreshed). Not yet verified on a phone. Suite 697 pass.

## Android API 36 (Nov 1): default target/compile SDK 35->36 (Play requires 36). AGP 8.7.3 warns only. Doodle Dance v6 AAB done.

## Nov 1: 53e34b7 (local): return key now fires on_submit_editing; ScrollView keyboard_dismiss_mode on iOS/Android. 699 pass.
- Nov 1: Android keyboard/focus fixes, `Linking.claimed`, TextInput no theme underline (694fee9). a14 on PyPI; a15 tagged (2c72fbf), publish needs user approval. 702 pass.
