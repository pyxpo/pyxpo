# Pyxpo progress
- Goal: from-scratch Python mobile framework, Expo parity. See DESIGN.md, PLAN.md, RELEASING.md. Tests: `.venv/bin/pytest -q`.
- Env quirks: host py3.9; no `timeout`; `sed -i ''`; no foreground sleep; `pkill -f GradleDaemon` before Android builds. Two iOS sims booted: use UDID D601942E-67CD-4C00-90E0-93886B61B288 (iPhone 17). Android emulator-5554 = AVD pyxpo35 (API 35), start with `-no-audio` (host CoreAudio crash on mic).
- Rules: no Co-Authored-By/Claude attribution in commits/PRs. Outward actions (release, PyPI, tag, push) need user go-ahead.
- Done+committed: runtime, bridge, shells, CLI, hot reload, router, prebuild, distribution, app config + plugins + build_properties, native module system, packages image-manipulator, image-picker, media-library, sharing, storage, file-system, secure-store (e2e both OS). Release 0.1.0a1 on PyPI (8 dists).
- 0.1.0a2 + 11 Tier 1 packages on PyPI Oct 16.

## Tier 1 packages pushed Oct 16.

## Remote push + remount fix: committed, tag v0.1.0a3 pushed
- notifications FCM/APNs, tools/send_push.py, Android remount fix.
- Released (Oct 19): core 0.1.0a3 + 0.1.0a4, pyxpo-notifications 0.1.0a2, pyxpo-dot-env 0.1.0a1 (renamed from pyxpo-env), pyxpo-google-mobile-ads 0.1.0a1.

## VS Code ext 0.1.0 on Marketplace (hand upload). Desktop/web targets pushed Oct 17.

## armeabi-v7a (Oct 19, pushed fe55e66): core 0.1.0a5 v7a runtime.

## doodle-puppet / birthday-sky (Oct 19, pushed): pose-detection pkg, TextInput stale-echo fix. Gradle hang: `JAVA_TOOL_OPTIONS=-Djava.net.preferIPv6Addresses=true`.

## AI Keyboard (pyxpo-apps/ai-keyboard): pushed. pyxpo-keyboard, pyxpo-speech, pyxpo-translate 0.1.0a1 on PyPI (Oct 29). README shots done (translate hero; keyboard hero + layouts). Open: S23 check of iOS layout + ML Kit; Phase 3 pyxpo-llm.

## Mac Catalyst + pyxpo-video (Oct 21-22): pushed. Catalyst ssl slice published in runtime 3.13.7-2 (_ssl, _hashlib checked).

## Package repos split (Oct 29)
- 29 repos pyxpo/pyxpo-<pkg>. ivishalchaubey invited.
- packages/ removed from monorepo. Clones live in ../pyxpo-packages/pyxpo-<pkg> (PYXPO_PACKAGES overrides). Each has tests/, ci.yml, release.yml (tag v<version>, env `pypi`), committed local.
- tools/build_packages.py --path/--tag, dev_install.sh clones missing + `--no-deps -e`. Core suite 564 pass; all 29 package suites pass.
- Oct 29 pushed: monorepo main, 29 package repos (+10 community/CI commits each: SECURITY, CONTRIBUTING, templates, badges, build job). `pypi` env + private vuln reporting on. ivishalchaubey collaborator on all.
- PyPI trusted publishers moved to pyxpo-<pkg>/release.yml. main rulesets on 30 repos. Org: GitHub refuses conversion of pyxpo.

- Core 0.1.0a9 on PyPI (Oct 29): native module contract 4, use_async awaits lambda coroutine. Tags v0.1.0a6-a8 never published (a6/a7 no macOS runner, a8 no sips on ubuntu); release tests now ubuntu + Pillow. Suite 565 pass.
- pyxpo-video 0.1.0a1 on PyPI (Oct 29). All 29 packages have trusted publishers.

## Run UX hardening (Oct 30, core 0.1.0a10)
- Dev port busy: `_dev_server` in cli.py tries next 20 ports unless --port given. `--device` flag (android serial/AVD, ios name/UDID).
- Android `ensure_device`: pins ANDROID_SERIAL, boots AVD when none connected (PYXPO_EMULATOR_ARGS), clear errors for unauthorized/offline/several devices. Runs before Gradle.
- iOS: Xcode 27 has no Simulator.app; `show_simulator` falls back to DeviceHub (com.apple.dt.Devices). `simctl bootstatus` after boot.
- Suite 575 pass + tests/test_android_devices.py. iOS e2e verified (port 8766 fallback). Android auto-boot e2e verified (Pixel_10).
