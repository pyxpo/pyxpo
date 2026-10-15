import Foundation
import Photos

/// Saves files to the photo library with their exact bytes (add-only access; the app can not read the library).
final class MediaLibraryModule: PxModule {
    static let moduleName = "MediaLibrary"

    required init() {}

    func call(_ ctx: PxModuleContext, _ method: String, _ args: [Any], _ reply: @escaping PxReply) {
        switch method {
        case "request_permission":
            let writeOnly = (args.first as? Bool) ?? true
            let level: PHAccessLevel = writeOnly ? .addOnly : .readWrite
            PHPhotoLibrary.requestAuthorization(for: level) { status in
                reply(["granted": status == .authorized || status == .limited], nil)
            }
        case "save":
            guard let p = args.first as? String else { reply(nil, "save: missing path"); return }
            let path = p.hasPrefix("file://") ? (URL(string: p)?.path ?? p) : p
            guard FileManager.default.fileExists(atPath: path) else { reply(nil, "file not found: \((path as NSString).lastPathComponent)"); return }
            PHPhotoLibrary.requestAuthorization(for: .addOnly) { status in
                guard status == .authorized || status == .limited else { reply(nil, "photo library permission denied"); return }
                PHPhotoLibrary.shared().performChanges({
                    let req = PHAssetCreationRequest.forAsset()
                    let opts = PHAssetResourceCreationOptions()
                    opts.shouldMoveFile = false
                    req.addResource(with: .photo, fileURL: URL(fileURLWithPath: path), options: opts)
                }) { ok, err in
                    if ok { reply(nil, nil) } else { reply(nil, err.map { "\($0.localizedDescription)" } ?? "save failed") }
                }
            }
        default:
            reply(nil, "unknown native call MediaLibrary.\(method)")
        }
    }
}
