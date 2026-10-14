# Pyxpo progress
- Goal: from-scratch Python mobile framework (no Kivy/BeeWare/Chaquopy). See DESIGN.md, PLAN.md. Tests: `.venv/bin/pytest -q` (224 pass).
- Env quirks: host py3.9 (core py3.9-compatible); no `timeout`; `sed -i ''`; iOS build ~10 min; no foreground sleep.
- Infra done+committed: CPython 3.13, C bridge/flexbox, Kotlin+Swift shells, CLI, hot reload, perf pass. Android verified, iOS renders only.
- Rules: no Co-Authored-By/Claude attribution in commits/PRs.
## RN-parity + expo-router milestone (UNCOMMITTED, in progress)
- Done: components/ and apis/ packages mirror react-native (pyxpo/__init__ 93 names); old ui/widgets/navigation/kit/theme/icons removed.
- Router done+tested: router/{discovery,matching,store,runtime,router,hooks,theme,screen,link,root,entry}, layouts/{header,slot,stack,tabs,drawer}. Entry = pyxpo.router.entry (native strings + cli switched). Legacy app/main.py still runs.
- Examples converted to app/ routes (counter, todo, rn_style); ui_components deleted. README/DESIGN updated.
- R9 hot reload with router DONE (Store.set_tree, App.hot_hooks, client base fix); 222 tests pass.
- A1+A9 partial DONE: Kotlin call() TextInput focus/blur/clear/set_selection, Linking can_open_url/open_settings, Vibration pattern/cancel; manifest <queries>; android build OK (not run on device).
- TODO: Android native A1-A9 remaining (TextInput onSelectionChange/onKeyPress, hit_slop, delay_long_press, pointer_events, RefreshControl, Text ellipsize/selectable/on_press, Image extras, StatusBar extras, Modal on_show, AppState/Linking/Vibration) then `pyxpo build android` in examples/counter + device check; D3 opus diff review; commit (plain msg).
- Gaps: iOS Swift controls + NavStack; Modal in hidden Stack screen; render error w/o boundary leaves partial ops; real-device fps unmeasured; SectionList no sticky headers.
- Device-verified (Android emu): Stack/Tabs/Drawer open+render, Switch, TextInput, FlatList, live hot reload, error overlay show/clear. Fixes: overlay ids must be < 2**30 (native CONTENT bit); launch() force-stops app so dev extras apply.
- Still unverified on device: Drawer item tap, edge pan, swipe-back, route add/delete reload, deep links, new call() cases, release/API24.
- Safe-area/gesture pass DONE: hooks Context.Consumer, SafeAreaInsets/FrameContext, use_safe_area_frame; pyxpo.safe_area (SafeAreaProvider); pyxpo.gesture_handler (Gesture.Pan/Tap/LongPress/Fling, Race/Simultaneous/Exclusive, GestureDetector); Drawer items use insets; iOS StatusBar.set_hidden. 228 tests pass. iOS tb app renders, no bottom strip seen; drawer open not tapped on iOS (no tap tool).
- Dev reload DONE: double-R (Android debuggable, 800ms window) / Cmd+R or double-R (iOS DEBUG) -> native event dev_reload -> App.reload (re-exec modules + remount, state resets). Android emu verified (count 2 -> 0). iOS Swift written, NOT built/run. launch() uses am start -S. 229 tests pass.
- TODO next: Animated audit vs RN, fps measure, Drawer/Tabs device taps, router tests, D3 review.
