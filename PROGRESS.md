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

## Remote push + remount fix: committed, tag v0.1.0a3 pushed
- notifications FCM/APNs token, plugin, tools/send_push.py. Android activity remount fix (process-wide runtime, `remount` event).
- Release run 38893625537 waits for user approval (pypi env). Then tag pkg/notifications/v0.1.0a2, user approves again.
- Later: real FCM e2e (~/.pyxpo-secrets/), missing packages batch, wheels CI.

## VS Code extension (editors/vscode) — committed 93d9ed6 + pushed, Oct 16
- TS, no deps beyond vscode types. src/pyscan.ts, analyze.ts, colors.ts, toml.ts, imports.ts (auto-import edits), extension.ts.
- data/pyxpo.json (incl. `exports` = pyxpo.__all__) from tools/gen_vscode_data.py; tests/test_vscode_data.py fails when stale.
- User bug "autocomplete not working": window in Restricted Mode, extension had no `capabilities.untrustedWorkspaces` so VS Code disabled it. Fixed (limited support; run commands + config validation need trust).
- Dev-mode extensions skip trust: only `npm run test:e2e:vsix` (installs packaged vsix, harness ext runs suite) proves it. Without capability: 9/15 fail, same as user screenshot.
- `npm test` 27/27; `test:e2e` and `test:e2e:vsix` 15/15 trusted + 15/15 Restricted Mode. vsix installed. Demo: scratchpad/pyxpo-demo (screen.py for auto-import).
- Logo: python coiled around a phone, transparent. Source editors/vscode/images/icon.svg; render with headless Chrome to logo-512.png, `sips -z 128 128` to icon.png. Same svg in pyxpo-web public/logo.svg (header/footer) + src/app/icon.png (favicon).
- Next: marketplace publish blocked: no vsce publisher login. User creates publisher `pyxpo` + Azure DevOps PAT (Marketplace: Manage), runs `npx @vscode/vsce login pyxpo` themselves; then `vsce publish`.
