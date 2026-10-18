# Pyxpo progress
- Goal: from-scratch Python mobile framework, Expo parity. See DESIGN.md, PLAN.md, RELEASING.md. Tests: `.venv/bin/pytest -q`.
- Env quirks: host py3.9 (package code must run on 3.9); no `timeout`; `sed -i ''`; no foreground sleep; `pkill -f GradleDaemon` before Android builds. Two iOS sims booted: use UDID D601942E-67CD-4C00-90E0-93886B61B288 (iPhone 17). Android emulator-5554 is now AVD Pixel_10 (API 37; pyxpo35 gone).
- Rules: no Co-Authored-By/Claude attribution in commits/PRs. Outward actions (release, PyPI, tag, push) need user go-ahead.
- Done+committed: runtime, bridge, shells, CLI, hot reload, router, prebuild, distribution, app config + plugins + build_properties, native module system, packages image-manipulator, image-picker, media-library, sharing, storage, file-system, secure-store (e2e both OS). Release 0.1.0a1 on PyPI (8 dists).
- 0.1.0a2 core + 11 Tier 1 packages (0.1.0a1) on PyPI, Oct 16. All pushed. PyPI install smoke: fresh venv + pyxpo create + all 11 modules, build + run 11/11 OK on Android emu and iOS sim. wheelhouse/ gitignored (tracked a1 wheel broke CI).

## Tier 1 packages: done, committed + pushed (Oct 16). Pattern: packages/<name>, tests/test_pkg_<name>.py, autolink.OFFICIAL, e2e via test-apps/tier1kit tools/*_selftest.sh.

## Remote push + remount fix: committed, tag v0.1.0a3 pushed
- notifications FCM/APNs token, plugin, tools/send_push.py. Android activity remount fix (process-wide runtime, `remount` event).
- Released (Oct 19): core 0.1.0a3 + 0.1.0a4, pyxpo-notifications 0.1.0a2, pyxpo-dot-env 0.1.0a1 (renamed from pyxpo-env), pyxpo-google-mobile-ads 0.1.0a1.
- Later: real FCM e2e (~/.pyxpo-secrets/), missing packages batch, wheels CI.

## VS Code extension (editors/vscode): committed + pushed, 0.1.0 live on Marketplace (publisher pyxpo, hand upload; bump version each upload).
- data/pyxpo.json from tools/gen_vscode_data.py; tests/test_vscode_data.py fails when stale. Restricted Mode needs `capabilities.untrustedWorkspaces`; prove with `npm run test:e2e:vsix`.

## Desktop apps (Oct 17, committed + pushed)
- Mac native = Catalyst, Windows native = WinUI 3 shell (windows/PyxpoShell), preview = `run desktop --preview`.
- Windows CI green (run 38975954256): app renders imagekit. Fix was PyxpoShell.pri copied to resources.pri.
- Windows open bugs (from CI home.png): Feather icons missing; card shadows draw grey rectangles, not rounded.

## Web target (Oct 17, pushed): run/build web.
## Responsive + layout + web dev tools (Oct 17, pushed)
- pyxpo/responsive.py breakpoints (xs..xxl), maps in style values/blocks; reconciler.refresh_responsive restyles without re-render.
- renderers/web/devtools.js: dev server only (`--no-devtools`), FAB panel, phone/tablet frames, rotate, custom size, zoom, scheme, platform (os override, reload), touch drag-scroll. app.js reads window.PYXPO_DEVICE(), `pyxpo-env` event, `pyxpo-statusbar` event. CDP e2e OK.
- Later: `[tool.pyxpo] breakpoints` config (devtools ruler reads PYXPO_CONFIG.breakpoints).
- Next: fix Windows icon/shadow bugs. Release with themes/web/responsive (0.1.0a3) needs user OK; then drop the "ships after 0.1.0a2" callouts in pyxpo-web.

## imagekit responsive + StyleSheet themes (Oct 17, pushed): src/pyxpo/themes.py, tests/test_themes.py.

## armeabi-v7a (Oct 19, pushed fe55e66)
- Client SM-M136B (M13 5G) runs 32-bit Android; APK had only arm64-v8a/x86_64, so "not compatible".
- Added v7a: build_cpython.py (patches android.py HOSTS), platforms/libs/cli (v7a optional tag), android.py stage drops v7a with a warning when no wheel (unless `abis` set), PyxpoRuntime.kt picks first shipped ABI. tests/test_android_abis.py. 857 pass.
- Done: v7a CPython built, imagekit APK has arm64-v8a+armeabi-v7a+x86_64, 64-bit OK on emulator, manifest entry added (tarball .cache/runtime-out). Next: user uploads v7a tarball to runtime-3.13.7-1, then core 0.1.0a5 release; client tests APK on M13.
