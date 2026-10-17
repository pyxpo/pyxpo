import UIKit

@main
class AppDelegate: UIResponder, UIApplicationDelegate {
    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        return true
    }

    func application(_ application: UIApplication, configurationForConnecting connectingSceneSession: UISceneSession,
                     options: UIScene.ConnectionOptions) -> UISceneConfiguration {
        let c = UISceneConfiguration(name: "Default", sessionRole: connectingSceneSession.role)
        c.delegateClass = SceneDelegate.self
        return c
    }
}

class SceneDelegate: UIResponder, UIWindowSceneDelegate {
    var window: UIWindow?
    private var applier: OpApplier?

    func scene(_ scene: UIScene, willConnectTo session: UISceneSession, options: UIScene.ConnectionOptions) {
        guard let ws = scene as? UIWindowScene else { return }
        let vc = PxRootViewController()
        vc.view.backgroundColor = .white
        let w = UIWindow(windowScene: ws)
        w.rootViewController = vc
        #if DEBUG
        // The simulator ignores its own dark setting under automation; this forces the trait so the theme path can be tested.
        if let m = ProcessInfo.processInfo.environment["PYXPO_APPEARANCE"] { w.overrideUserInterfaceStyle = m == "dark" ? .dark : .light }
        #endif
        w.makeKeyAndVisible()
        window = w
        #if targetEnvironment(macCatalyst)
        ws.title = Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String ?? ""
        ws.sizeRestrictions?.minimumSize = CGSize(width: 360, height: 480)
        #endif

        let rt = PyxpoRuntime.shared()
        vc.view.layoutIfNeeded()
        let size = vc.view.bounds.size
        var env = OpApplier.envJson(window: size, screen: UIScreen.main.bounds.size,
                                    dark: vc.traitCollection.userInterfaceStyle == .dark,
                                    insets: vc.view.safeAreaInsets)
        if let u = options.urlContexts.first?.url { env["initial_url"] = u.absoluteString }
        #if DEBUG
        if let u = ProcessInfo.processInfo.environment["PYXPO_INITIAL_URL"], !u.isEmpty { env["initial_url"] = u }  // simctl has no openurl without a prompt
        #endif
        if let d = try? JSONSerialization.data(withJSONObject: env) { rt.envJSON = String(data: d, encoding: .utf8) }
        let ap = OpApplier(container: vc.view) { rt.dispatchEvent($0) }
        applier = ap
        rt.onOps = { [weak ap] json in ap?.apply(json) }
        #if DEBUG
        vc.onDevReload = { [weak ap] in ap?.devReload() }
        #endif

        let bundle = Bundle.main.resourcePath ?? Bundle.main.bundlePath  // Contents/Resources in the Mac (Catalyst) app
        var appRoot = bundle + "/app_root"
        #if DEBUG
        if let url = ProcessInfo.processInfo.environment["PYXPO_DEV_URL"], !url.isEmpty {
            appRoot = Self.writableCopy(of: appRoot)
        }
        #endif
        rt.start(withHome: bundle + "/python", paths: [appRoot, bundle + "/app_packages"], module: "pyxpo.router.entry")
    }

    #if targetEnvironment(macCatalyst)
    /// On the Mac, closing the window quits the app: the Python runtime serves one window and cannot start twice.
    func sceneDidDisconnect(_ scene: UIScene) { exit(0) }
    #endif

    /// Deep link while running (cold-start links are replayed once Python is up).
    func scene(_ scene: UIScene, openURLContexts contexts: Set<UIOpenURLContext>) {
        for c in contexts { applier?.openURL(c.url.absoluteString) }
    }

    /// The bundle is read-only on device; hot reload needs a writable copy of the app tree.
    private static func writableCopy(of root: String) -> String {
        let fm = FileManager.default
        let caches = NSSearchPathForDirectoriesInDomains(.cachesDirectory, .userDomainMask, true)[0]
        let dest = caches + "/pyxpo/app_root"
        try? fm.removeItem(atPath: dest)
        try? fm.createDirectory(atPath: caches + "/pyxpo", withIntermediateDirectories: true)
        try? fm.copyItem(atPath: root, toPath: dest)
        return dest
    }
}

/// Root controller: owns the status bar appearance (`StatusBar.set_style` from Python).
final class PxRootViewController: UIViewController {
    static weak var shared: PxRootViewController?
    private var barStyle: UIStatusBarStyle = .darkContent

    override func viewDidLoad() { super.viewDidLoad(); Self.shared = self }
    override var preferredStatusBarStyle: UIStatusBarStyle { barStyle }
    var onDevReload: (() -> Void)?
    private var lastR = Date.distantPast

    #if DEBUG
    // Key presses go to the first responder only. With no text field focused there is none (the Mac app, a hardware
    // keyboard), so the controller takes that role, and takes it back when a text field stops editing.
    override var canBecomeFirstResponder: Bool { true }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        becomeFirstResponder()
        for name in [UITextField.textDidEndEditingNotification, UITextView.textDidEndEditingNotification] {
            NotificationCenter.default.addObserver(self, selector: #selector(reclaimKeys), name: name, object: nil)
        }
    }

    @objc private func reclaimKeys() {
        DispatchQueue.main.async { [weak self] in  // after focus has moved on (Tab to the next field)
            guard let self = self, self.view.window != nil, !Self.textInputFocused(in: self.view) else { return }
            self.becomeFirstResponder()
        }
    }

    private static func textInputFocused(in v: UIView) -> Bool {
        if v.isFirstResponder && v is UITextInput { return true }
        return v.subviews.contains { textInputFocused(in: $0) }
    }

    /// Dev builds: R twice (hardware keyboard / simulator / Mac app) or Cmd+R reloads, as in React Native.
    override func pressesBegan(_ presses: Set<UIPress>, with event: UIPressesEvent?) {
        for p in presses {
            guard let k = p.key, k.charactersIgnoringModifiers.lowercased() == "r",
                  k.modifierFlags.isDisjoint(with: [.control, .alternate]) else { continue }
            let now = Date()
            if k.modifierFlags.contains(.command) || now.timeIntervalSince(lastR) < 0.8 {
                lastR = .distantPast
                onDevReload?()
                return
            }
            lastR = now
        }
        super.pressesBegan(presses, with: event)
    }
    #endif
    private var barHidden = false
    override var prefersStatusBarHidden: Bool { barHidden }
    override var preferredStatusBarUpdateAnimation: UIStatusBarAnimation { .fade }

    /// `StatusBar.set_hidden` from Python.
    func setBarHidden(_ hidden: Bool) {
        barHidden = hidden
        UIView.animate(withDuration: 0.2) { self.setNeedsStatusBarAppearanceUpdate() }
    }

    /// light=true means light (white) glyphs for dark backgrounds.
    func setBarStyle(light: Bool) {
        barStyle = light ? .lightContent : .darkContent
        setNeedsStatusBarAppearanceUpdate()
    }
}
