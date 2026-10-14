# Pyxpo progress
- Goal: from-scratch Python mobile framework (no Kivy/BeeWare/Chaquopy). See DESIGN.md, PLAN.md. Tests: `.venv/bin/pytest -q` (232 pass).
- Env quirks: host py3.9; no `timeout`; `sed -i ''`; iOS build few min; no foreground sleep.
- Rules: no Co-Authored-By/Claude attribution in commits/PRs.
- Done+committed earlier: CPython 3.13, C bridge/flexbox, Kotlin+Swift shells, CLI, hot reload, RN-parity components/apis, expo-router (Stack/Tabs/Drawer), safe-area, gesture handler, deep links, dev reload (RR/Cmd+R).
- This pass (iOS stable): a11y labels+roles for Drawer/Tabs/Pressable (iOS+Android), native iOS PxNav (push/pop animation, left-edge swipe-back via pop_gesture), PYXPO_APPEARANCE debug override, double-R window 0.8s, run ios Simulator message fix.
- iOS XCUITest (tests/ios_ui/E2E.swift): 5/5 pass on sim: Flow, Cmd+R/RR reload, Stack push + swipe-back pop + edge drawer, dark/light theme pixel check, warm deep link.
- Note: sim ignores its dark setting under automation, so theme tested via PYXPO_APPEARANCE.
- Open: Android rebuild+device verify of a11y change and deep link; release build/real device signing; Swift controls audit; Modal in hidden Stack screen; SectionList sticky headers; real-device fps; D3 opus full-diff review; go-live + real-world project.
