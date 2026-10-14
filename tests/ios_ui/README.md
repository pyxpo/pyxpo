# iOS UI end-to-end test

XCUITest used to verify touch, Drawer, Tabs and double-R / Cmd+R reload on the iOS simulator.

It targets a Drawer app (index counter "Cnt: n" with an Add button, Tabs with "One"/"Two") whose index.py shows a
module-load timestamp. Start a dev server on port 8765 with token `tok123`, add a `UITests` target
(`type: bundle.ui-testing`, `TEST_TARGET_NAME: PyxpoApp`, `PRODUCT_NAME: UITests`) to the generated shell's
project.yml, then run `xcodebuild test -scheme PyxpoApp -destination 'id=<simulator udid>'`.
