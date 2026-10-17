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

## Desktop apps (Oct 17, committed + pushed)
- Mac native = Catalyst, Windows native = WinUI 3 shell (windows/PyxpoShell), preview = `run desktop --preview`.
- Windows CI green (run 38975954256): app renders imagekit. Fix was PyxpoShell.pri copied to resources.pri.
- Windows open bugs (from CI home.png): Feather icons missing; card shadows draw grey rectangles, not rounded.

## Web target (Oct 17, committed locally, NOT pushed)
- `pyxpo run web` (dev server, SPA fallback, SSE reload) / `pyxpo build web` (static build/web, 404.html, hashed zip).
- Pyodide 0.27.7 in page; reconciler = virtual DOM (keyed, LIS moves); app.js applies ops; History.sync from RouterRoot.
- Module web backends: packages/*/web.py (image-picker, image-manipulator via Pillow micropip, media-library, sharing).
- browser.boot puts linked module list in env (require_linked failed on web before).
- `[tool.pyxpo.web]` title/base/packages/pyodide_url in schema. README "Web" section.
- E2E (headless Chrome CDP, scratchpad/cdp): nav, back/forward, deep link, 404, pick 2 photos, resize, Save, Share OK.
- Tests: tests/test_web_build.py, store href test. Full suite 561 pass.
- Web feel (Oct 17): Stack on web = no animation/gesture, all pages mounted (visibility hidden + inert, scroll and focus kept); Link -> <a href> overlay; pressables tabindex/role, Enter/Space, hover, focus-visible; web header arrow-left 56px. router.runtime.on_web(). E2E OK in Chrome.

## Responsive + layout + web dev tools (Oct 17, committed locally, NOT pushed)
- pyxpo/responsive.py breakpoints (xs..xxl), maps in style values/blocks; reconciler.refresh_responsive restyles without re-render.
- hooks use_breakpoint/use_breakpoint_value/use_media_query; components/layout.py Container Row Col Grid GridItem Flex HStack VStack Center Spacer Show Hide. tests/test_responsive.py.
- renderers/web/devtools.js: dev server only (`--no-devtools`), FAB panel, phone/tablet frames, rotate, custom size, zoom, scheme, platform (os override, reload), touch drag-scroll. app.js reads window.PYXPO_DEVICE(), `pyxpo-env` event, `pyxpo-statusbar` event. CDP e2e OK.
- Full suite 588 pass.
- Devtools v2 (bbb8073): side toolbar (rotate/zoom/fit/1:1/theme/back/reload), zoom 20-300% via slider, ctrl+wheel/pinch, corner grip; panel redesign; device sits left of open panel.
- Later: `[tool.pyxpo] breakpoints` config (devtools ruler reads PYXPO_CONFIG.breakpoints).
- Next: user OK to push; fix Windows icon/shadow bugs.

## imagekit responsive + StyleSheet refactor (Oct 17, UNCOMMITTED: user said do not commit)
- Responsive layout (Container/GridRow/Col/Grid) in imagekit.
- Unistyles-3-style themes in core: src/pyxpo/themes.py, `StyleSheet.configure/create(lambda theme, rt)/setTheme`, dynamic styles, `useAppTheme` (router.useTheme name taken). Reconciler re-styles on theme/insets/scheme/bp change via style_key, no re-render. imagekit migrated (no makeStyles). tests/test_themes.py, README "Themes". 597 pass. Web verified light/dark/phone/desktop.
