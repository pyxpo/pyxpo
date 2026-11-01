import ImageIO
import UIKit

/// Loads images off the main thread: files, `asset:name`, `data:` URIs and http(s) URLs (URLCache disk cache).
/// Decoding happens on a background queue with ImageIO, so scrolling never decodes on the main thread. With a
/// target size the bitmap is cut down to what the view shows; the UIImage keeps the source size in points.
final class Images {
    private let cache: NSCache<NSString, UIImage> = {
        let c = NSCache<NSString, UIImage>()
        c.totalCostLimit = Int(min(ProcessInfo.processInfo.physicalMemory / 16, 128 << 20))
        return c
    }()
    private let queue = DispatchQueue(label: "pyxpo.images", qos: .userInitiated, attributes: .concurrent)
    // callbacks of loads in flight, by cache key; touched on the main thread only
    private var waiting: [String: [(UIImage?, String?) -> Void]] = [:]

    /// `px` is the view size in pixels; zero on a side means unknown, and the image decodes whole.
    func load(_ uri: String, px: CGSize = .zero, _ done: @escaping (UIImage?, String?) -> Void) {
        let key = px.width >= 1 && px.height >= 1 ? "\(uri)@\(Int(px.width))x\(Int(px.height))" : uri
        if let hit = cache.object(forKey: key as NSString) { done(hit, nil); return }
        // a grid shows the same photo in many cells at once: one decode serves every waiting cell
        if waiting[key] != nil { waiting[key]!.append(done); return }
        waiting[key] = [done]
        let finish: (UIImage?, String?) -> Void = { [weak self] img, err in
            DispatchQueue.main.async {
                guard let self = self else { return }
                if let img = img, let cg = img.cgImage {
                    self.cache.setObject(img, forKey: key as NSString, cost: cg.bytesPerRow * cg.height)
                }
                for cb in self.waiting.removeValue(forKey: key) ?? [] { cb(img, err) }
            }
        }
        if uri.hasPrefix("http://") || uri.hasPrefix("https://") {
            guard let url = URL(string: uri) else { finish(nil, "bad url"); return }
            URLSession.shared.dataTask(with: url) { data, _, error in
                if let d = data, let img = Images.decode(d, px) { finish(img, nil) }
                else { finish(nil, error?.localizedDescription ?? "decode failed") }
            }.resume()
            return
        }
        queue.async {
            var data: Data?
            if uri.hasPrefix("data:"), let r = uri.range(of: "base64,") {
                data = Data(base64Encoded: String(uri[r.upperBound...]), options: .ignoreUnknownCharacters)
            } else if uri.hasPrefix("asset:") {
                let name = String(uri.dropFirst(6))
                data = Bundle.main.resourcePath.flatMap { FileManager.default.contents(atPath: $0 + "/" + name) }
            } else {
                data = FileManager.default.contents(atPath: uri.hasPrefix("file://") ? String(uri.dropFirst(7)) : uri)
            }
            if let d = data, let img = Images.decode(d, px) { finish(img, nil) } else { finish(nil, "cannot load \(uri.prefix(60))") }
        }
    }

    /// Decodes now (not lazily at first draw). The short side is kept at least the target, so an aspect-fill
    /// view never upscales. The scale makes `size` the source size, as `UIImage(data:)` would report it.
    static func decode(_ data: Data, _ px: CGSize) -> UIImage? {
        guard let src = CGImageSourceCreateWithData(data as CFData, [kCGImageSourceShouldCache: false] as CFDictionary),
              let p = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any],
              let w = (p[kCGImagePropertyPixelWidth] as? NSNumber)?.doubleValue,
              let h = (p[kCGImagePropertyPixelHeight] as? NSNumber)?.doubleValue, w >= 1, h >= 1
        else { return UIImage(data: data) }
        let long = max(w, h)
        var side = long
        if px.width >= 1 && px.height >= 1 {
            let o = (p[kCGImagePropertyOrientation] as? NSNumber)?.intValue ?? 1
            let (ow, oh) = o >= 5 ? (h, w) : (w, h)
            side = min(long, (long * max(Double(px.width) / ow, Double(px.height) / oh)).rounded(.up))
        }
        let opts: [CFString: Any] = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceShouldCacheImmediately: true,
            kCGImageSourceThumbnailMaxPixelSize: side,
        ]
        guard let cg = CGImageSourceCreateThumbnailAtIndex(src, 0, opts as CFDictionary) else { return UIImage(data: data) }
        return UIImage(cgImage: cg, scale: CGFloat(long) / CGFloat(max(cg.width, cg.height)), orientation: .up)
    }
}
