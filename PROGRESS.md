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
- dist/ios now has ios-arm64 device slice too (build_cpython.py --host both); old sim-only copy in scratchpad.
- Not verified: Android pre-31 system splash (API 30 image downloading, slow), iOS dark/tinted icon on home screen (simctl cannot toggle), team-signed device install (needs user's Apple team).
- configdemo pyproject.toml temporarily modified (automatic style, bars hidden); original in scratchpad configdemo.pyproject.orig.
- Test app: test-apps/configdemo (gitignored): splash+dark+landscape, demo plugin plugins/demo.py, build_properties minify on. Android pkg com.example.configdemo.droid, iOS com.example.configdemo.

## Storage packages (done)
- packages/storage (pure Python, SQLite, MMKV shape + AsyncStorage names, sync; hooks), file-system (expo File/Directory/Paths + legacy; native download), secure-store (Keychain / Keystore AES-GCM). All in autolink.OFFICIAL.
- E2E: test-apps/storagekit (gitignored) tools/android_selftest.sh + tools/ios_selftest.sh: ALL OK both runs (persistence) on emulator + simulator; hook tap persists after restart (Android).
- Fixes found by e2e: iOS empty AppIcon set when no icon (actool failed); iOS requireAuthentication without enrolled biometrics now errors like Android.
- Biometric flow verified: Face ID enrolled on simulator, fingerprint on emulator (PIN 1111). Selftest answers prompts via cache/sk_prompt marker (match/cancel); set+get+cancel ALL OK both OS. iOS fix: get now runs LAContext.evaluatePolicy itself (simulator keychain ignored ACL, never prompted).
- testID wired like React Native: iOS accessibilityIdentifier, Android view.tag + viewIdResourceName (uiautomator resource-id). Verified: XCUITest finds "tap-button" (taps persist after relaunch); Android tap by resource-id 3->6.
- Review fixes: folder copy onto/into itself now raises ValueError (was deleting source); delete of symlink-to-folder removes link only.
- Not verified: real devices.

## Prebuild parity (d00f2e8)
- prebuild ships gradlew (8.10.2) + makes ios/PyxpoApp.xcodeproj; `pyxpo stage` runs from Gradle task / Xcode pre-build script (PYXPO_PYTHON, skip via PYXPO_STAGED); pyxpo-gen synced not rmtree'd; app.zip per build type.
- Verified on test-apps/prebuilddemo: ./gradlew assembleRelease+assembleDebug, release APK runs + tap; code edit picked by incremental assembleDebug; plain xcodebuild sim build runs; pyxpo build android skips stage task.
- Host quirk: Java here cannot download Gradle (timeout); wrapper dist seeded from .cache/gradle-8.10.2.

## Next apps
PDF Utility, Last Done, Keep Until, My Measurements (spec apps-list.pdf).
