# Pyxpo progress
- Goal: from-scratch Python mobile framework, Expo parity. See DESIGN.md, PLAN.md, RELEASING.md. Tests: `.venv/bin/pytest -q` (403 pass).
- Env quirks: host py3.9; no `timeout`; `sed -i ''`; iOS build few min; no foreground sleep; `pkill -f GradleDaemon` before Android builds.
- Rules: no Co-Authored-By/Claude attribution in commits/PRs. Outward actions (gh release, PyPI, tag/git push, MIT confirm) need user go-ahead.
- Done+committed: runtime, bridge, shells, CLI, hot reload, components/apis, router, prebuild, distribution code (runtime downloads, `pyxpo doctor`, release workflow; real GitHub/PyPI upload NOT done), native module system + packages/ (image-manipulator, image-picker, media-library, sharing; Expo-shaped, iOS selftest 25/25, Android ALL OK).
- ImageKit (test-apps/imagekit) client-ready on Android standalone APK. Not verified: iOS UI taps, real device. Open: metadata strip re-encodes; late result preview.

## App config (Expo app.json equivalent) — [tool.pyxpo] + app_config.py
- Committed: core, iOS/Android wiring, icons, bars/appearance, splash, Constants (6779024), image tests, config plugins (a6f84ef), build_properties (46ddba1).
- Config plugins verified e2e on configdemo both OS (Info.plist key, xcconfig, dangerous mod, largeHeap, uses-feature, res string, gradle.properties block).
- build_properties verified: release APK with R8 minify+shrink launches, renders, taps work (keep rules `dev.pyxpo.**` + native methods in pyxpo-gen/proguard-pyxpo.pro).
- Done: headless checker tools/e2e_app_config.py, dev-server native-config-changed warning, full-diff review (fixes: shrink needs minify, iOS full-screen KeyError, plugin import errors, res name check), ImageKit Android selftest ALL OK (MediaStore 32-clash fallback name). Docs deferred.
- Verified (Oct 15): light+dark splash Android API 35 + iOS sim; hidden status/nav bars on splash + app (fix 346c2ed: applyStatusBar in onCreate); iOS AppIcon light/dark/tinted in Assets.car; entitlements: sim binary has associated-domains, device build (iphoneos) ad-hoc codesigned keeps them, Release settings point CODE_SIGN_ENTITLEMENTS.
- Release APK without keystore now debug-signed (834180f), fixes "App not installed" on phone; user must re-prebuild (edited build.gradle.kts gets .pyxpo-new) and uninstall old app.
- dist/ios now has ios-arm64 device slice too (build_cpython.py --host both); old sim-only copy in scratchpad.
- Android API 30 (pre-31 layer-list) splash verified light+dark, bars hidden, app renders (AVD pyxpo30).
- Release APK without keystore debug-signed (834180f).
- Not verified: iOS dark/tinted icon on home screen (simctl cannot toggle), team-signed device install (needs user's Apple team).
- Test app: test-apps/configdemo (gitignored): splash+dark+landscape, demo plugin plugins/demo.py, build_properties minify on. Android pkg com.example.configdemo.droid, iOS com.example.configdemo.

## Storage packages (done)
- packages/storage, file-system, secure-store; e2e selftests ALL OK both OS incl. biometrics; testID wired. Real devices not verified.

## Prebuild parity (d00f2e8)
- prebuild ships gradlew + ios xcodeproj; Gradle task / Xcode script run `pyxpo stage`. Verified on test-apps/prebuilddemo. Gradle dist seeded from .cache/gradle-8.10.2.

## Release 0.1.0a1 (done)
- MIT, github.com/pyxpo/pyxpo, PyPI account pyxpo, trusted publishing. All 8 packages on PyPI (pyxpo + 7 pyxpo-*), sharing confirmed Oct 16. Runbook: RELEASING.md.
- Repo now lives in pyxpo/ subfolder; website is sibling repo ../pyxpo-web (Next.js, local commit only, see its PROGRESS.md).

## Next apps
PDF Utility, Last Done, Keep Until, My Measurements (spec apps-list.pdf).
