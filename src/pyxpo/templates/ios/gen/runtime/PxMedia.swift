import Foundation
import UIKit

struct PxMediaError: Error {
    let message: String
    init(_ message: String) { self.message = message }
}

/// Native side of pyxpo's media APIs (ImageTools, ImagePicker, MediaLibrary, Share). `OpApplier` hands unknown
/// native calls here. Heavy work runs on one serial queue; replies always go back on the main thread.
enum PxMedia {
    typealias Reply = (Any?, String?) -> Void

    static let queue = DispatchQueue(label: "pyxpo.media")

    /// Returns false when `module.method` is not a media call.
    static func handle(_ module: String, _ method: String, _ args: [Any], root: UIView, reply: @escaping Reply) -> Bool {
        switch "\(module).\(method)" {
        case "ImageTools.ping":
            background(reply) { "pong" }
        default:
            return false
        }
        return true
    }

    /// Runs `work` on the media queue and replies on main with its value, or its error message.
    static func background(_ reply: @escaping Reply, _ work: @escaping () throws -> Any?) {
        queue.async {
            var value: Any?
            var message: String?
            do { value = try work() }
            catch let e as PxMediaError { message = e.message }
            catch { message = "\(error)" }
            DispatchQueue.main.async { reply(value, message) }
        }
    }
}
