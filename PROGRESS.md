# Pyxpo progress
- Goal: from-scratch Python mobile framework, Expo parity. See DESIGN.md, PLAN.md, RELEASING.md. Tests: `.venv/bin/pytest -q`.
- Env quirks: host py3.9 (package code must run on 3.9); no `timeout`; `sed -i ''`; no foreground sleep; `pkill -f GradleDaemon` before Android builds. Two iOS sims booted: use UDID D601942E-67CD-4C00-90E0-93886B61B288 (iPhone 17). Android emulator-5554 = AVD pyxpo35 (API 35), start with `-no-audio` (host CoreAudio crash on mic).
- Rules: no Co-Authored-By/Claude attribution in commits/PRs. Outward actions (release, PyPI, tag, push) need user go-ahead.
- Done+committed: runtime, bridge, shells, CLI, hot reload, router, prebuild, distribution, app config + plugins + build_properties, native module system, packages image-manipulator, image-picker, media-library, sharing, storage, file-system, secure-store (e2e both OS). Release 0.1.0a1 on PyPI (8 dists).
- 0.1.0a2 core + 11 Tier 1 packages (0.1.0a1) on PyPI, Oct 16. All pushed. PyPI install smoke: fresh venv + pyxpo create + all 11 modules, build + run 11/11 OK on Android emu and iOS sim. wheelhouse/ gitignored (tracked a1 wheel broke CI).

## Tier 1 packages: done, committed + pushed (Oct 16). Pattern: packages/<name>, tests/test_pkg_<name>.py, autolink.OFFICIAL, e2e via test-apps/tier1kit tools/*_selftest.sh.

## Remote push + remount fix: committed, tag v0.1.0a3 pushed
- notifications FCM/APNs, tools/send_push.py, Android remount fix.
- Released (Oct 19): core 0.1.0a3 + 0.1.0a4, pyxpo-notifications 0.1.0a2, pyxpo-dot-env 0.1.0a1 (renamed from pyxpo-env), pyxpo-google-mobile-ads 0.1.0a1.

## VS Code extension (editors/vscode): pushed, 0.1.0 on Marketplace (hand upload; bump version). data/pyxpo.json from tools/gen_vscode_data.py.

## Desktop (Catalyst, WinUI 3, `--preview`), web target + devtools + themes: pushed Oct 17. Later: breakpoints.

## armeabi-v7a (Oct 19, pushed fe55e66)
- v7a runtime; dropped when a wheel is missing (unless `abis`). tests/test_android_abis.py.
- Released core 0.1.0a5 with v7a runtime. Open: client tests APK on M13.
- Release dex fail ("located outside the root directory") = project moved, stale .gradle paths. Guard `_drop_moved_gradle_state` (marker .gradle/pyxpo-root) in prebuild/build; Gradle stage task only warns. imagekit assembleRelease OK after clean.
- iOS App Store upload: prune_site; iPad 4 orientations.

## From pyxpo-apps doodle-puppet / birthday-sky (Oct 19, pushed)
- packages/pose-detection (ML Kit / Vision; photos + videos) + README, tests, autolink. iOS sim: Vision Code=9, `available` probes a blank image so it reports False there. iPhone unchecked.
- TextInput stale-echo fix (OpApplier.kt/.swift, web app.js), Android focus after pop, web restyle keeps --vars + spinner colour.
- Gradle hang: `JAVA_TOOL_OPTIONS=-Djava.net.preferIPv6Addresses=true` (IPv4 broken).

## AI Keyboard (pyxpo-apps/ai-keyboard, Oct 19, pushed)
- packages/keyboard (pyxpo-keyboard): Android InputMethodService, native Kotlin keys; phase 1 emulator-verified. App PROGRESS.md has detail.
- ON HOLD (Oct 21, user asked to pause). All committed local, NOT pushed: 9628c0b, 7331bc6, 4c122c1 (speech live + kept audio), 80c36f5 (keyboard panel, iOS layout, icons), 8faecf4 (pyxpo-translate). Suite 988 pass.
- Release: keyboard + speech + translate deps -> `pyxpo>=0.1.0a6` (contract 4). Install translate with `pip --no-deps -e`.
- Resume: push on user go-ahead; translate README hero.png missing (needs real demo screenshot); keyboard README screenshots redo for new layout; S23 check of iOS layout + ML Kit; Phase 3 pyxpo-llm.
