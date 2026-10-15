import Foundation
import Photos
import ImageIO
import AVFoundation
import UniformTypeIdentifiers

/// Photo library permissions and adding photos and videos with their exact bytes. Adding needs only add-only access.
final class MediaLibraryModule: PxModule {
    static let moduleName = "MediaLibrary"

    required init() {}

    func call(_ ctx: PxModuleContext, _ method: String, _ args: [Any], _ reply: @escaping PxReply) {
        switch method {
        case "get_permission", "request_permission":
            let writeOnly = (args.first as? Bool) ?? false
            let level: PHAccessLevel = writeOnly ? .addOnly : .readWrite
            guard method == "request_permission", PHPhotoLibrary.authorizationStatus(for: level) == .notDetermined else {
                reply(Self.state(PHPhotoLibrary.authorizationStatus(for: level)), nil); return
            }
            // iOS terminates the app when access is requested without the matching usage description.
            let key = writeOnly ? "NSPhotoLibraryAddUsageDescription" : "NSPhotoLibraryUsageDescription"
            if Bundle.main.object(forInfoDictionaryKey: key) == nil { reply(nil, "photo library access needs \(key) in Info.plist"); return }
            PHPhotoLibrary.requestAuthorization(for: level) { reply(Self.state($0), nil) }
        case "save", "create":
            guard let p = args.first as? String else { reply(nil, "\(method): missing path"); return }
            let path = p.hasPrefix("file://") ? (URL(string: p)?.path ?? p) : p
            guard FileManager.default.fileExists(atPath: path) else { reply(nil, "file not found: \((path as NSString).lastPathComponent)"); return }
            let url = URL(fileURLWithPath: path)
            let video = Self.isVideo(url)
            PHPhotoLibrary.requestAuthorization(for: .addOnly) { status in
                guard status == .authorized || status == .limited else { reply(nil, "photo library permission denied"); return }
                var id: String?
                PHPhotoLibrary.shared().performChanges({
                    let req = PHAssetCreationRequest.forAsset()
                    let opts = PHAssetResourceCreationOptions()
                    opts.shouldMoveFile = false
                    opts.originalFilename = url.lastPathComponent
                    req.addResource(with: video ? .video : .photo, fileURL: url, options: opts)
                    id = req.placeholderForCreatedAsset?.localIdentifier
                }) { ok, err in
                    guard ok else { reply(nil, err.map { "\($0.localizedDescription)" } ?? "save failed"); return }
                    if method == "save" { reply(nil, nil); return }
                    // Described from the source file: with add-only access the new PHAsset can not be fetched back.
                    reply(Self.describe(url, id: id ?? "", video: video), nil)
                }
            }
        default:
            reply(nil, "unknown native call MediaLibrary.\(method)")
        }
    }

    private static func state(_ s: PHAuthorizationStatus) -> [String: Any] {
        switch s {
        case .authorized: return ["status": "granted", "canAskAgain": true, "accessPrivileges": "all"]
        case .limited: return ["status": "granted", "canAskAgain": true, "accessPrivileges": "limited"]
        case .notDetermined: return ["status": "undetermined", "canAskAgain": true, "accessPrivileges": "none"]
        default: return ["status": "denied", "canAskAgain": false, "accessPrivileges": "none"]  // denied, restricted
        }
    }

    private static func isVideo(_ url: URL) -> Bool {
        guard let t = UTType(filenameExtension: url.pathExtension.lowercased()) else { return false }
        return t.conforms(to: .movie) || t.conforms(to: .video)
    }

    private static func describe(_ url: URL, id: String, video: Bool) -> [String: Any] {
        var w = 0, h = 0
        var duration = 0.0
        if video {
            let av = AVURLAsset(url: url)
            if let t = av.tracks(withMediaType: .video).first {
                let sz = t.naturalSize.applying(t.preferredTransform)
                (w, h) = (Int(abs(sz.width).rounded()), Int(abs(sz.height).rounded()))
            }
            let secs = CMTimeGetSeconds(av.duration)
            duration = secs.isFinite ? secs : 0
        } else if let s = CGImageSourceCreateWithURL(url as CFURL, nil),
                  let props = CGImageSourceCopyPropertiesAtIndex(s, 0, nil) as? [CFString: Any] {
            let pw = props[kCGImagePropertyPixelWidth] as? Int ?? 0
            let ph = props[kCGImagePropertyPixelHeight] as? Int ?? 0
            let o = props[kCGImagePropertyOrientation] as? Int ?? 1
            (w, h) = o >= 5 && o <= 8 ? (ph, pw) : (pw, ph)
        }
        return ["id": id, "uri": "ph://" + id, "mediaType": video ? "video" : "photo", "width": w, "height": h,
                "duration": duration, "filename": url.lastPathComponent]
    }
}
