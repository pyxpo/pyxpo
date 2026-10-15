# Pyxpo progress
- Goal: from-scratch Python mobile framework, Expo parity. See DESIGN.md, PLAN.md, RELEASING.md. Tests: `.venv/bin/pytest -q` (400 pass).
- Env quirks: host py3.9; no `timeout`; `sed -i ''`; iOS build few min; no foreground sleep; `pkill -f GradleDaemon` before Android builds.
- Rules: no Co-Authored-By/Claude attribution in commits/PRs. Outward actions (gh release, PyPI, tag/git push, MIT confirm) need user go-ahead.
- Done+committed: runtime, bridge, shells, CLI, hot reload, components/apis, router, prebuild, distribution code (runtime downloads, `pyxpo doctor`, release workflow; real GitHub/PyPI upload NOT done), native module system + packages/ (image-manipulator, image-picker, media-library, sharing; Expo-shaped, iOS selftest 25/25, Android ALL OK).
- ImageKit (test-apps/imagekit) client-ready on Android standalone APK. Not verified: iOS UI taps, real device. Open: metadata strip re-encodes; late result preview.

## App config (Expo app.json equivalent) — [tool.pyxpo] + app_config.py
- Committed: core, iOS/Android wiring, icons, bars/appearance, splash, Constants (6779024), image tests, config plugins (a6f84ef), build_properties (46ddba1).
- Config plugins verified e2e on configdemo both OS (Info.plist key, xcconfig, dangerous mod, largeHeap, uses-feature, res string, gradle.properties block).
- build_properties verified: release APK with R8 minify+shrink launches, renders, taps work (keep rules `dev.pyxpo.**` + native methods in pyxpo-gen/proguard-pyxpo.pro).
- Done: headless checker tools/e2e_app_config.py, dev-server native-config-changed warning, full-diff review (fixes: shrink needs minify, iOS full-screen KeyError, plugin import errors, res name check), ImageKit Android selftest ALL OK (MediaStore 32-clash fallback name). Docs deferred.
- Not verified: light-mode splash on device, Android pre-31/v31 system splash, hidden-bar paths, iOS home-screen icon shots, entitlements in signed iOS app.
- Test app: test-apps/configdemo (gitignored): splash+dark+landscape, demo plugin plugins/demo.py, build_properties minify on. Android pkg com.example.configdemo.droid, iOS com.example.configdemo.

## Storage packages (done)
- packages/storage (pure Python, SQLite, MMKV shape + AsyncStorage names, sync; hooks), file-system (expo File/Directory/Paths + legacy; native download), secure-store (Keychain / Keystore AES-GCM). All in autolink.OFFICIAL.
- E2E: test-apps/storagekit (gitignored) tools/android_selftest.sh + tools/ios_selftest.sh: ALL OK both runs (persistence) on emulator + simulator; hook tap persists after restart (Android).
- Fixes found by e2e: iOS empty AppIcon set when no icon (actool failed); iOS requireAuthentication without enrolled biometrics now errors like Android.
- Not verified: biometric prompt flow (no enrolled biometrics on emulator/simulator), real devices.

## Next apps
PDF Utility, Last Done, Keep Until, My Measurements (spec apps-list.pdf).
