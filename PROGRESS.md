# Pyxpo progress
- Goal: from-scratch Python mobile framework (no Kivy/BeeWare/Chaquopy); all libs via mobile wheels. See DESIGN.md, PLAN.md.
- Done M1: pure-Python core in src/pyxpo, CLI (create, run desktop, doctor, add-lib), 17 tests pass (`.venv/bin/pytest`).
- Done M2 (steps 12-17): own CPython 3.13.7 cross-build (native/android/build_cpython.py, arm64-v8a + x86_64), C bridge (native/common/pyxpo_bridge.*), Kotlin shell template (src/pyxpo/templates/android), `pyxpo build|run android` (src/pyxpo/build/android.py).
- VERIFIED on Pixel_10 emulator (API 37, arm64): Counter demo renders, button tap increments count.
- Decisions: JSON ops batch over Channel; root id 1 implicit (OpApplier pre-creates it); edge-to-edge insets applied in MainActivity; sys.path = home/lib/python3.13 + lib-dynload + app + site; libs extracted to filesDir/pyxpo/<hash>.
- Env quirks: Gradle needs `-Djava.net.preferIPv6Addresses=true` (in template gradle.properties); host py3.9 too old for android.py (uses 3.12); no `timeout` on macOS.
- Open: rebuild CPython libs with 16 KB ELF alignment (LDFLAGS added to build_cpython.py, not yet rebuilt); numpy example (needs android_24 wheel; may need pyxpo-wheels index); test API 24 / x86_64 dlopen; build APK with both ABIs; test for build/android helpers; final opus-engineer diff review (JNI/GIL/threading).
- Next: M3 iOS (steps 18-20), M4 wheels index + hot reload.
