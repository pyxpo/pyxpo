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
    /// Sends a `module` event to Python (`pyxpo.modules.on_event(name, payload)`).
    func emit(_ name: String, _ payload: [String: Any])
}

/// A native module. `moduleName` is the bridge module name Python calls (for example "ImagePicker").
/// `call` runs on the main thread: do heavy work elsewhere and finish with `reply`.
/// Reply with an error string to fail the call; an unreplied call hangs its Python await.
protocol PxModule: AnyObject {
    static var moduleName: String { get }
    init()
    func call(_ ctx: PxModuleContext, _ method: String, _ args: [Any], _ reply: @escaping PxReply)
}

/// Routes `Module.method` calls to the native modules linked into this app (`pxModules`). Main thread only.
final class PxModuleHost: PxModuleContext {
    private var instances: [String: PxModule] = [:]
    private var types: [String: PxModule.Type] = [:]
    private var kept: [Int: AnyObject] = [:]
    private var nextToken = 1
    private weak var root: UIView?
    private let emitEvent: (String, [String: Any]) -> Void

    init(root: UIView, emit: @escaping (String, [String: Any]) -> Void) {
        self.root = root
        self.emitEvent = emit
        for t in pxModules { types[t.moduleName] = t }
    }

    static var names: [String] { pxModules.map { $0.moduleName }.sorted() }

    /// Returns false when no linked module has this name.
    func call(_ module: String, _ method: String, _ args: [Any], _ reply: @escaping PxReply) -> Bool {
        guard let type = types[module] else { return false }
        let m = instances[module] ?? type.init()
        instances[module] = m
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

    func emit(_ name: String, _ payload: [String: Any]) { emitEvent(name, payload) }
}
