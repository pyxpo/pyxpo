# iOS UI end-to-end test

XCUITest that verifies, on the iOS simulator: tap, Drawer open and item tap (including accessibility labels),
Tabs, Stack push, swipe-back pop, left-edge drawer pan, dark and light theme, double-R and Cmd+R reload, and a
warm-start deep link.

It targets a Drawer app (index counter "Cnt: n" with an Add button and a module-load timestamp, Tabs "One"/"Two",
and a Stack with a "Push detail" link to a detail screen).

Setup:
1. Start a dev server on port 8765 with token `tok123`.
2. Add a `UITests` target (`type: bundle.ui-testing`, `TEST_TARGET_NAME: PyxpoApp`, `PRODUCT_NAME: UITests`) to the
   generated shell's project.yml and copy E2E.swift into `UITests/`. `pyxpo build ios` regenerates the shell and
   removes both, so redo this after each build, then run `xcodegen generate`.
3. For the warm deep link test, run a host watcher that opens the URL the test writes:
   `(until [ -s /tmp/e2e_openurl ]; do sleep 1; done; xcrun simctl openurl booted "$(cat /tmp/e2e_openurl)") &`
4. `xcodebuild test -scheme PyxpoApp -destination 'id=<simulator udid>'`

The simulator ignores its own dark setting under automation, so the theme test launches the app with the
DEBUG-only `PYXPO_APPEARANCE=dark|light` environment variable.
