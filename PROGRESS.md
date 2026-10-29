# Pyxpo progress
- Goal: from-scratch Python mobile framework, Expo parity. See DESIGN.md, PLAN.md, RELEASING.md. Tests: `.venv/bin/pytest -q`.
- Env quirks: host py3.9 (package code must run on 3.9); no `timeout`; `sed -i ''`; no foreground sleep; `pkill -f GradleDaemon` before Android builds. Two iOS sims booted: use UDID D601942E-67CD-4C00-90E0-93886B61B288 (iPhone 17). Android emulator-5554 = AVD pyxpo35 (API 35), start with `-no-audio` (host CoreAudio crash on mic).
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

## AI Keyboard (pyxpo-apps/ai-keyboard, Oct 19, pushed)
- packages/keyboard (pyxpo-keyboard): Android InputMethodService, native Kotlin keys; phase 1 emulator-verified. App PROGRESS.md has detail.
- ON HOLD (Oct 21, user asked to pause). All committed local, NOT pushed: 9628c0b, 7331bc6, 4c122c1 (speech live + kept audio), 80c36f5 (keyboard panel, iOS layout, icons), 8faecf4 (pyxpo-translate). Suite 988 pass.
- Release: keyboard + speech + translate deps -> `pyxpo>=0.1.0a6` (contract 4). Install translate with `pip --no-deps -e`.
- Resume: push on user go-ahead; translate README hero.png missing (needs real demo screenshot); keyboard README screenshots redo for new layout; S23 check of iOS layout + ML Kit; Phase 3 pyxpo-llm.

## Mac Catalyst fixes from insta-shorts native app (Oct 21, local commits, not pushed)
- 9ecf4eb `include` + build mode to app_config. ecc6100: ad-hoc catalyst ENABLE_HARDENED_RUNTIME=NO, `_internal/apple.py` `_scproxy` stand-in, runtime UTF-8 mode (launchd gives no LANG). Suite 992 pass.
- efff616 (local): Catalyst slice now has _ssl/_hashlib (OpenSSL 3.5.9 static, built by build_catalyst_python.sh from .cache/openssl-3.5.9); apple.py sets SSL_CERT_FILE=/etc/ssl/cert.pem. Published `ios` runtime asset lacks ssl until republished (needs go-ahead).

## pyxpo-video (Oct 22, local, not pushed)
- db65f37 layout max_width fix. 7715035 packages/video (VideoView, play/pause/seek, README+shots) + web /file byte ranges. iOS sim + Android emu verified; Catalyst visual unchecked. Suite 1009 pass.
- Mac app icon (Oct 22, local): icons.py adds mac idiom AppIcon renditions (16-512 @1x/@2x); Catalyst showed generic icon with iPad-only set.

## Package repos split (Oct 29)
- 29 repos pyxpo/pyxpo-<pkg> (public, squash only). ivishalchaubey invited (pyxpo personal account, no Admin role).
- packages/ removed from monorepo. Clones live in ../pyxpo-packages/pyxpo-<pkg> (PYXPO_PACKAGES overrides). Each has tests/, ci.yml, release.yml (tag v<version>, env `pypi`), committed local.
- tools/build_packages.py --path/--tag, dev_install.sh clones missing + `--no-deps -e`. Core suite 564 pass; all 29 package suites pass.
- Open (go-ahead needed): push monorepo main (4b089ec + removal commit) and 29 package repos. Then: `pypi` env per repo, repoint PyPI trusted publishers to pyxpo-<pkg>/release.yml, branch protection, convert pyxpo to org.
