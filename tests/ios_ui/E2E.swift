import XCTest

final class E2E: XCTestCase {
    func launchApp(_ extra: [String: String] = [:]) -> XCUIApplication {
        let app = XCUIApplication()
        for (k, v) in extra { app.launchEnvironment[k] = v }
        app.launchEnvironment["PYXPO_DEV_URL"] = "http://127.0.0.1:8765"
        app.launchEnvironment["PYXPO_DEV_TOKEN"] = "tok123"
        app.launch()
        return app
    }
    func shot(_ app: XCUIApplication, _ name: String) {
        let a = XCTAttachment(screenshot: app.screenshot()); a.name = name; a.lifetime = .keepAlways; add(a)
        try? app.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: "/tmp/e2e_\(name).png"))
    }
    func label(_ app: XCUIApplication, _ prefix: String) -> XCUIElement {
        app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", prefix)).firstMatch
    }

    func testFlow() {
        let app = launchApp()
        XCTAssertTrue(label(app, "Cnt: 0").waitForExistence(timeout: 30), "home renders")
        shot(app, "1-home")
        // touch: press Add twice
        let add = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'add'")).firstMatch
        XCTAssertTrue(add.waitForExistence(timeout: 5), "add button")
        add.tap(); add.tap()
        XCTAssertTrue(label(app, "Cnt: 2").waitForExistence(timeout: 5), "tap increments")
        shot(app, "2-after-add")
        // drawer open via hamburger
        app.coordinate(withNormalizedOffset: CGVector(dx: 0.06, dy: 0.10)).tap()
        sleep(1); shot(app, "3a-drawer-try"); try? app.debugDescription.write(toFile: "/tmp/e2e_tree.txt", atomically: true, encoding: .utf8)
        app.coordinate(withNormalizedOffset: CGVector(dx: 0.10, dy: 0.207)).tap()  // drawer item "Tabs"
        sleep(2)
        shot(app, "4-tabs")
        app.coordinate(withNormalizedOffset: CGVector(dx: 0.75, dy: 0.95)).tap()  // tab "Two"
        sleep(1)
        shot(app, "5-tab-two")
        XCTAssertFalse(label(app, "Cnt:").exists, "left Home for Tabs")
        // double-R reload resets state: go back via drawer to Home then check count reset
        app.typeKey("r", modifierFlags: [])
        usleep(150_000)
        app.typeKey("r", modifierFlags: [])
        sleep(3)
        shot(app, "6-after-rr")
        XCTAssertTrue(label(app, "Cnt: 0").waitForExistence(timeout: 10), "R R reloads to Home with reset state")
    }

    func testCmdR() {
        let app = launchApp()
        XCTAssertTrue(label(app, "Cnt: 0").waitForExistence(timeout: 30))
        let add = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'add'")).firstMatch
        add.tap()
        XCTAssertTrue(label(app, "Cnt: 1").waitForExistence(timeout: 5))
        app.typeKey("r", modifierFlags: .command)
        XCTAssertTrue(label(app, "Cnt: 0").waitForExistence(timeout: 10), "Cmd+R reloads")
    }

    func testStackSwipeBackAndEdgeDrawer() {
        let app = launchApp()
        XCTAssertTrue(label(app, "Cnt: 0").waitForExistence(timeout: 30))
        // edge pan opens the drawer (retry: a XCUITest drag can be dropped while the app is still settling)
        func edgePan(_ y: CGFloat) {
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.0, dy: y))
                .press(forDuration: 0.1, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.8, dy: y)),
                       withVelocity: .slow, thenHoldForDuration: 0.2)
        }
        let stackItem = app.buttons["Stack"]
        var attempts = 0
        while attempts < 3 && !stackItem.exists { attempts += 1; edgePan(0.5); _ = stackItem.waitForExistence(timeout: 3) }
        try? "edge attempts: \(attempts)".write(toFile: "/tmp/e2e_attempts.txt", atomically: true, encoding: .utf8)
        XCTAssertTrue(stackItem.waitForExistence(timeout: 5), "edge pan opens drawer; items have accessibility labels")
        XCTAssertTrue(app.buttons["Tabs"].exists && app.buttons["About"].exists)
        shot(app, "10-edge-drawer")
        stackItem.tap()
        sleep(2); shot(app, "10b-stack"); try? app.debugDescription.write(toFile: "/tmp/e2e_tree2.txt", atomically: true, encoding: .utf8)
        let push = app.links["Push detail"]
        XCTAssertTrue(push.waitForExistence(timeout: 5), "stack home")
        push.tap()
        XCTAssertTrue(label(app, "Detail screen").waitForExistence(timeout: 5), "pushed")
        shot(app, "11-pushed")
        // swipe back from the left edge
        app.coordinate(withNormalizedOffset: CGVector(dx: 0.0, dy: 0.5))
            .press(forDuration: 0.1, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.8, dy: 0.5)))
        XCTAssertTrue(app.links["Push detail"].waitForExistence(timeout: 5), "swipe back pops to stack home")
        sleep(2)
        shot(app, "12-popped"); try? app.debugDescription.write(toFile: "/tmp/e2e_tree3.txt", atomically: true, encoding: .utf8)
        XCTAssertFalse(label(app, "Detail screen").exists, "popped screen leaves the tree")
    }

    /// Brightness (0...1) of the screenshot pixel at a fractional position.
    func luma(_ app: XCUIApplication, _ fx: CGFloat, _ fy: CGFloat) -> CGFloat {
        guard let cg = app.screenshot().image.cgImage else { return -1 }
        var px = [UInt8](repeating: 0, count: 4)
        let ctx = CGContext(data: &px, width: 1, height: 1, bitsPerComponent: 8, bytesPerRow: 4,
                            space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
        ctx.draw(cg, in: CGRect(x: -fx * CGFloat(cg.width), y: -(1 - fy) * CGFloat(cg.height), width: CGFloat(cg.width), height: CGFloat(cg.height)))
        return (CGFloat(px[0]) + CGFloat(px[1]) + CGFloat(px[2])) / (3 * 255)
    }

    func testDarkModeStatusBarAndTheme() {
        var app = launchApp(["PYXPO_APPEARANCE": "dark"])
        XCTAssertTrue(label(app, "Cnt: 0").waitForExistence(timeout: 30))
        sleep(1)
        shot(app, "20-dark")
        XCTAssertLessThan(luma(app, 0.5, 0.6), 0.3, "dark theme: screen background is dark")
        XCTAssertLessThan(luma(app, 0.5, 0.09), 0.3, "dark theme: header is dark")
        app.terminate()
        app = launchApp(["PYXPO_APPEARANCE": "light"])
        XCTAssertTrue(label(app, "Cnt: 0").waitForExistence(timeout: 30))
        sleep(1)
        shot(app, "21-light")
        XCTAssertGreaterThan(luma(app, 0.5, 0.6), 0.7, "light theme: screen background is light")
    }

    func testWarmDeepLink() {
        let app = launchApp()
        XCTAssertTrue(label(app, "Cnt: 0").waitForExistence(timeout: 30))
        XCUIDevice.shared.press(.home)
        sleep(1)
        // The simulator sandbox cannot run simctl; tests/ios_ui/run.sh watches this file and runs
        // `xcrun simctl openurl booted <url>` from the host.
        try? "com.example.tb://tabs/two".write(toFile: "/tmp/e2e_openurl", atomically: true, encoding: .utf8)
        let sb = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let open = sb.buttons["Open"]
        if open.waitForExistence(timeout: 10) { open.tap() }  // iOS asks once per scheme; skipped when already allowed
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 10))
        XCTAssertTrue(label(app, "Tab two screen").waitForExistence(timeout: 10), "warm deep link navigates")
        shot(app, "30-warm-link")
    }
}
