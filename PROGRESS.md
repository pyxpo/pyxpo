# Pyxpo progress
- Goal: from-scratch Python mobile framework, Expo parity. See DESIGN.md, PLAN.md, RELEASING.md. Tests: `.venv/bin/pytest -q`.
- Env quirks: host py3.9 (package code must run on 3.9); no `timeout`; `sed -i ''`; no foreground sleep; `pkill -f GradleDaemon` before Android builds. Two iOS sims booted: use UDID D601942E-67CD-4C00-90E0-93886B61B288 (iPhone 17). Android emulator-5554 is now AVD Pixel_10 (API 37; pyxpo35 gone).
- Rules: no Co-Authored-By/Claude attribution in commits/PRs. Outward actions (release, PyPI, tag, push) need user go-ahead.
- Done+committed: runtime, bridge, shells, CLI, hot reload, router, prebuild, distribution, app config + plugins + build_properties, native module system, packages image-manipulator, image-picker, media-library, sharing, storage, file-system, secure-store (e2e both OS). Release 0.1.0a1 on PyPI (8 dists).
- 0.1.0a2 core + 11 Tier 1 packages (0.1.0a1) on PyPI, Oct 16. All pushed. PyPI install smoke: fresh venv + pyxpo create + all 11 modules, build + run 11/11 OK on Android emu and iOS sim. wheelhouse/ gitignored (tracked a1 wheel broke CI).

## Tier 1 packages: done, committed + pushed (Oct 16). Pattern: packages/<name>, tests/test_pkg_<name>.py, autolink.OFFICIAL, e2e via test-apps/tier1kit tools/*_selftest.sh.

## Remote push + remount fix: committed, tag v0.1.0a3 pushed
- notifications FCM/APNs token, plugin, tools/send_push.py. Android activity remount fix (process-wide runtime, `remount` event).
- Release run 38893625537 waits for user approval (pypi env). Then tag pkg/notifications/v0.1.0a2, user approves again.
- Later: real FCM e2e (~/.pyxpo-secrets/), missing packages batch, wheels CI.

## VS Code extension (editors/vscode): committed + pushed, 0.1.0 live on Marketplace (publisher pyxpo, hand upload; bump version each upload).
- data/pyxpo.json from tools/gen_vscode_data.py; tests/test_vscode_data.py fails when stale. Restricted Mode needs `capabilities.untrustedWorkspaces`; prove with `npm run test:e2e:vsix`.

## Desktop apps (Oct 17, uncommitted)
- Web preview: `pyxpo run desktop --preview` (src/pyxpo/renderers/web, Chrome --app). Module calls via pkg `desktop.py` backends.
- Mac native = Catalyst: tools/build_catalyst_python.sh adds slice; build/ios.py kind "catalyst"; imagekit renders. Tests: tests/test_build_catalyst.py.
- Windows native = WinUI 3 C# shell (windows/PyxpoShell) + pyxpo_native.dll (windows/native) + CPython embeddable. build/windows.py stages build/windows/<Name>/. WindowsChannel: shell answers builtin calls, rest run in desktop.py. Docs windows/README.md. `[tool.pyxpo.windows]` title/size in schema.
- Shell compiles on mac (dotnet build -p:EnableWindowsTargeting=true -p:WindowsAppSDKSelfContained=false -p:ApplicationManifest=), never run on real Windows. CI .github/workflows/windows.yml (build shell + imagekit, screenshot artifact) = first real test.
- Tests: tests/test_windows.py 21 pass; full suite 538 pass.
- Catalyst full check done: selftest 24/24, home + 7 tool screens + result screen OK, picker works. Fixed iOS bug: Image background_color (BoxLayer sublayer) covered the picture; now on layer.backgroundColor + corner clip (OpApplier.swift paintBox). Android/Windows not affected.
- Next: user OK to commit + push, run windows workflow, fix what CI shows.
