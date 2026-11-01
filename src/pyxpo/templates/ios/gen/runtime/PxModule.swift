import UIKit

/// Completes one call. Safe from any thread; the host hops to the main thread. `value` must be JSON-compatible.
typealias PxReply = (_ value: Any?, _ error: String?) -> Void

/// What the app gives a native module.
protocol PxModuleContext: AnyObject {
    /// The view controller to present system UI from (topmost presented one).
    func presenter() -> UIViewController?
    /// Keeps `object` alive until `release` (delegates that UIKit holds weakly, for example picker delegates).
    func retain(_ object: AnyObject) -> Int
    func release(_ token: Int)
    /// Sends a `module` event to Python (`pyxpo.modules.on_event(name, payload)`). Safe from any thread.
    func emit(_ name: String, _ payload: [String: Any])
    /// The mounted native view with this tag (the Python handle's node id), if a module made it.
    func view(_ tag: Int) -> PxNativeView?
}

/// A view a module provides (`pyxpo.module_api.native_view`). Made, updated and disposed on main.
/// The layout engine sizes it from its style, like a plain View; it has no children.
protocol PxNativeView: AnyObject {
    var view: UIView { get }
    /// Changed props (JSON values; `on_<event>` props are `true` while Python listens) and removed prop names.
    /// The first call has every initial prop.
    func update(_ props: [String: Any], _ removed: [String])
    /// The view left the tree for good.
    func dispose()
}

extension PxNativeView {
    func dispose() {}
}

/// A module that provides native view types. `emit(name, value)` calls the view's `on_<name>` prop in Python.
protocol PxViewModule: PxModule {
    static var viewTypes: [String] { get }
    func makeView(_ ctx: PxModuleContext, _ type: String, _ emit: @escaping (String, Any?) -> Void) -> PxNativeView
}

/// A native module. `moduleName` is the bridge module name Python calls (for example "ImagePicker").
/// `call` runs on the main thread: do heavy work elsewhere and finish with `reply`.
/// Reply with an error string to fail the call; an unreplied call hangs its Python await.
protocol PxModule: AnyObject {
    static var moduleName: String { get }
    /// JSON-compatible values Python reads synchronously (`pyxpo.module_api.constants`). Built once at startup, on main.
    static var constants: [String: Any] { get }
    init()
    func call(_ ctx: PxModuleContext, _ method: String, _ args: [Any], _ reply: @escaping PxReply)
}

extension PxModule {
    static var constants: [String: Any] { [:] }
}

/// A module that must start with the app, before Python runs (for example to receive the notification tap that
/// launched it). Called once on main, right after `application(_:didFinishLaunchingWithOptions:)`, with its options.
protocol PxAppLaunchObserver {
    static func appDidFinishLaunching(_ options: [AnyHashable: Any]?)
}

/// Called by the ObjC runtime at launch (`PyxpoRuntime +load`); the user's AppDelegate needs no code for it.
@objc(PxAppLaunch) final class PxAppLaunch: NSObject {
    @objc static func run(_ options: NSDictionary?) {
        for t in pxModules { (t as? PxAppLaunchObserver.Type)?.appDidFinishLaunching(options as? [AnyHashable: Any]) }
    }
}

/// Routes `Module.method` calls to the native modules linked into this app (`pxModules`). Main thread only.
final class PxModuleHost: PxModuleContext {
    private var instances: [String: PxModule] = [:]
    private var types: [String: PxModule.Type] = [:]
    private var kept: [Int: AnyObject] = [:]
    private var views: [Int: PxNativeView] = [:]
    private var nextToken = 1
    private weak var root: UIView?
    private let emitEvent: (String, [String: Any]) -> Void

    init(root: UIView, emit: @escaping (String, [String: Any]) -> Void) {
        self.root = root
        self.emitEvent = emit
        for t in Self.all { types[t.moduleName] = t }
    }

    /// Built into the runtime (no package needed), then the ones listed in [tool.pyxpo] modules.
    static let all: [PxModule.Type] = [ImageViewerModule.self] + pxModules

    static var names: [String] { all.map { $0.moduleName }.sorted() }

    /// {module name: constants} for modules that export any.
    static var constants: [String: Any] {
        var out: [String: Any] = [:]
        for t in all {
            let c = t.constants
            if !c.isEmpty && JSONSerialization.isValidJSONObject(c) { out[t.moduleName] = c }
        }
        return out
    }

    private func instance(_ module: String) -> PxModule? {
        guard let type = types[module] else { return nil }
        let m = instances[module] ?? type.init()
        instances[module] = m
        return m
    }

    /// Makes a module view, or returns nil when no linked module provides `type`.
    func makeView(_ type: String, _ tag: Int, _ emit: @escaping (String, Any?) -> Void) -> PxNativeView? {
        guard let t = Self.all.first(where: { ($0 as? PxViewModule.Type)?.viewTypes.contains(type) == true }),
              let m = instance(t.moduleName) as? PxViewModule else { return nil }
        let v = m.makeView(self, type, emit)
        views[tag] = v
        return v
    }

    func dropView(_ tag: Int) { views.removeValue(forKey: tag)?.dispose() }

    func view(_ tag: Int) -> PxNativeView? { views[tag] }

    /// Returns false when no linked module has this name.
    func call(_ module: String, _ method: String, _ args: [Any], _ reply: @escaping PxReply) -> Bool {
        guard let m = instance(module) else { return false }
        var done = false
        m.call(self, method, args) { v, e in
            DispatchQueue.main.async {
                if done { return }
                done = true
                reply(v, e)
            }
        }
        return true
    }

    func presenter() -> UIViewController? {
        var top = root?.window?.rootViewController
        while let p = top?.presentedViewController { top = p }
        return top
    }

    func retain(_ object: AnyObject) -> Int {
        let t = nextToken
        nextToken += 1
        kept[t] = object
        return t
    }

    func release(_ token: Int) { kept[token] = nil }

    func emit(_ name: String, _ payload: [String: Any]) {
        let send = emitEvent
        DispatchQueue.main.async { send(name, payload) }
    }
}
