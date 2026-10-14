import XCTest

final class E2E: XCTestCase {
    func launchApp() -> XCUIApplication {
        let app = XCUIApplication()
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
}
