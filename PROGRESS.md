# Pyxpo progress
- Goal: from-scratch Python mobile framework, Expo parity. See DESIGN.md, PLAN.md, RELEASING.md. Tests: `.venv/bin/pytest -q`.
- Env quirks: host py3.9 (package code must run on 3.9); no `timeout`; `sed -i ''`; no foreground sleep; `pkill -f GradleDaemon` before Android builds. Two iOS sims booted: use UDID D601942E-67CD-4C00-90E0-93886B61B288 (iPhone 17). Android emulator-5554 is now AVD Pixel_10 (API 37; pyxpo35 gone).
- Rules: no Co-Authored-By/Claude attribution in commits/PRs. Outward actions (release, PyPI, tag, push) need user go-ahead.
- Done+committed: runtime, bridge, shells, CLI, hot reload, router, prebuild, distribution, app config + plugins + build_properties, native module system, packages image-manipulator, image-picker, media-library, sharing, storage, file-system, secure-store (e2e both OS). Release 0.1.0a1 on PyPI (8 dists).
- 0.1.0a2 core + 11 Tier 1 packages (0.1.0a1) on PyPI, Oct 16. All pushed. PyPI install smoke: fresh venv + pyxpo create + all 11 modules, build + run 11/11 OK on Android emu and iOS sim. wheelhouse/ gitignored (tracked a1 wheel broke CI).

## Tier 1 packages (all built, Oct 16) — committed + pushed
- Core changes (constants, module views, launch observer, AppState, gradle_properties) all committed.
- Each package: packages/<name> (py + ios swift + android kt), tests/test_pkg_<name>.py (FakeBridge), add name to autolink.OFFICIAL, e2e via test-apps/tier1kit selftest (pattern: test-apps/storagekit tools/*_selftest.sh).
- Status: haptics, device, application, localization, network, fetch, sqlite, web-browser, location: done, unit + e2e iOS/Android (details in each README). fetch test server tools/fetch_server.py :8765. web-browser Android 15+: BAL + freezer, test closes tab via host `tabback`.
- tier1kit harness: tools/ios_selftest.sh|android_selftest.sh [sections]; NOBUILD=1 (Python changes need rebuild); host actions via cache/t1_req -> t1_ack. Android web-browser prep sets Chrome flags (skip first-run). Android python stdout: logcat tag python.stdout.

## Remote push (uncommitted, Oct 16)
- notifications: FCM (Android) + APNs (iOS) device token, token listener, unregister, plugin `pyxpo_notifications.plugin` (googleServicesFile, mode, enableBackgroundRemoteNotifications). NATIVE_CONTRACT 3 (Android onNewIntent). tools/send_push.py = FCM HTTP v1 sender (stdlib + openssl).
- pytest 500 pass. Android + iOS notifications selftest ALL OK (local, tap, background, simctl push; token says not configured). Next: README/CHANGELOG, real FCM e2e (needs ~/.pyxpo-secrets/google-services.json + service-account.json).
- Fixed core bug (uncommitted): Android activity recreate / back+relaunch in same process crashed (nativeStart twice, SIGABRT). Now PyxpoRuntime.get() is process-wide; new activity calls attach(applier, env) -> `remount` event -> Python App._native_remount (env update, anim native_reset, Mark(n) op, reload). OpApplier drops non-call ops until mark n. Verified on emu: font_scale recreate x2 + back/relaunch, same pid, UI back. Unit test test_native_remount_mounts_again_on_new_renderer.
