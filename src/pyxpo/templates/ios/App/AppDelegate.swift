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
        let vc = UIViewController()
        vc.view.backgroundColor = .white
        let w = UIWindow(windowScene: ws)
        w.rootViewController = vc
        w.makeKeyAndVisible()
        window = w

        let rt = PyxpoRuntime.shared()
        let ap = OpApplier(container: vc.view) { rt.dispatchEvent($0) }
        applier = ap
        rt.onOps = { [weak ap] json in ap?.apply(json) }

        let bundle = Bundle.main.bundlePath
        var appRoot = bundle + "/app_root"
        #if DEBUG
        if let url = ProcessInfo.processInfo.environment["PYXPO_DEV_URL"], !url.isEmpty {
            appRoot = Self.writableCopy(of: appRoot)
        }
        #endif
        rt.start(withHome: bundle + "/python", paths: [appRoot, bundle + "/app_packages"], module: "app.main")
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
