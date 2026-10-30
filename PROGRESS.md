# Pyxpo progress
- Goal: from-scratch Python mobile framework, Expo parity. See DESIGN.md, PLAN.md, RELEASING.md. Tests: `.venv/bin/pytest -q`.
- Env quirks: host py3.9; no `timeout`; `sed -i ''`; no foreground sleep; `pkill -f GradleDaemon` before Android builds. Two iOS sims booted: use UDID D601942E-67CD-4C00-90E0-93886B61B288 (iPhone 17). Android emulator-5554 = AVD pyxpo35 (API 35), start with `-no-audio` (host CoreAudio crash on mic).
- Rules: no Co-Authored-By/Claude attribution in commits/PRs. Outward actions (release, PyPI, tag, push) need user go-ahead.
- Done+committed: runtime, bridge, shells, CLI, hot reload, router, prebuild, distribution, app config + plugins + build_properties, native module system, packages image-manipulator, image-picker, media-library, sharing, storage, file-system, secure-store (e2e both OS). Release 0.1.0a1 on PyPI (8 dists).
- 0.1.0a2 + 11 Tier 1 pkgs on PyPI Oct 16.

## Remote push + remount fix: committed, tag v0.1.0a3 pushed
- notifications FCM/APNs, tools/send_push.py, Android remount fix.
- Released (Oct 19): core 0.1.0a3 + 0.1.0a4, pyxpo-notifications 0.1.0a2, pyxpo-dot-env 0.1.0a1 (renamed from pyxpo-env), pyxpo-google-mobile-ads 0.1.0a1.

## Oct 17-19: VS Code ext 0.1.0 (hand upload), desktop/web targets, armeabi-v7a runtime (core 0.1.0a5).

## doodle-puppet / birthday-sky (Oct 19, pushed): pose-detection pkg, TextInput stale-echo fix. Gradle hang: `JAVA_TOOL_OPTIONS=-Djava.net.preferIPv6Addresses=true`.

## AI Keyboard (pyxpo-apps/ai-keyboard): pushed. pyxpo-keyboard, pyxpo-speech, pyxpo-translate 0.1.0a1 on PyPI (Oct 29). README shots done (translate hero; keyboard hero + layouts). Open: S23 check of iOS layout + ML Kit; Phase 3 pyxpo-llm.

## Mac Catalyst + pyxpo-video (Oct 21-22): pushed. Catalyst ssl slice published in runtime 3.13.7-2 (_ssl, _hashlib checked).

## Package repos split (Oct 29)
- 29 repos pyxpo/pyxpo-<pkg>.
- packages/ removed from monorepo. Clones live in ../pyxpo-packages/pyxpo-<pkg> (PYXPO_PACKAGES overrides). Each has tests/, ci.yml, release.yml (tag v<version>, env `pypi`), committed local.
- tools/build_packages.py --path/--tag, dev_install.sh clones missing + `--no-deps -e`. Core suite 564 pass; all 29 package suites pass.
- Oct 29 pushed: monorepo + 29 package repos (community/CI files). `pypi` env + private vuln reporting on.
- PyPI trusted publishers moved to pyxpo-<pkg>/release.yml. main rulesets on 30 repos. Org: GitHub refuses conversion of pyxpo.

- Core 0.1.0a9 on PyPI (Oct 29): native module contract 4, use_async awaits lambda coroutine. Tags v0.1.0a6-a8 never published (a6/a7 no macOS runner, a8 no sips on ubuntu); release tests now ubuntu + Pillow. Suite 565 pass.
- pyxpo-video 0.1.0a1 on PyPI (Oct 29). All 29 packages have trusted publishers.

## Core 0.1.0a10 (Oct 30): dev port fallback, --device flag, Android ensure_device/AVD boot, iOS DeviceHub fallback.
- 0.1.0a11 on PyPI: iOS runtime extract symlink-chain fix.

## Oct 30 release batch
- On PyPI: pyxpo-image-manipulator 0.1.0a2, pyxpo-image-cropper 0.1.0a1 (new repo pyxpo/pyxpo-image-cropper, settings+ruleset+pypi env+pvr done).
- Core 0.1.0a12 on PyPI. `pypi` env in core repo has required reviewer: user approves each release.

## 6 new package repos (Oct 30): all on PyPI 0.1.0a1
- pyxpo/pyxpo-{rich-editor,query,intl,svg,google-sign-in,apple-authentication}: settings, ruleset, pypi env, pvr, collaborator ivishalchaubey (Write). Trusted publishers active.
- Core 0.1.0a13 on PyPI (Oct 30). Release = bump __version__ + regen editors/vscode/data/pyxpo.json (test_vscode_data checks it).
- fetch/secure-store/storage 0.1.0a2 on PyPI (Oct 30, floor pyxpo>=0.1.0a4).
- Next: README screenshots (rich-editor + 4 others); device tests iOS sim/emulator/S23.

## Stability pass (Oct 31, uncommitted): Gradle wedge auto-retry + `pyxpo clean [android|ios]`; include-package hot reload (iOS ok); iOS ships checked-hash .pyc (ios.compile_pyc), cmskite launch 30s->12s first, 8s->6s warm. Suite 603 pass.
