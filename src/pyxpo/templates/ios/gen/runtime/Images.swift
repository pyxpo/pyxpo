import UIKit

/// Loads images off the main thread: files, `asset:name`, `data:` URIs and http(s) URLs (URLCache disk cache).
final class Images {
    private let cache = NSCache<NSString, UIImage>()
    private let queue = DispatchQueue(label: "pyxpo.images", qos: .userInitiated, attributes: .concurrent)

    func load(_ uri: String, _ done: @escaping (UIImage?, String?) -> Void) {
        if let hit = cache.object(forKey: uri as NSString) { done(hit, nil); return }
        let finish: (UIImage?, String?) -> Void = { [weak self] img, err in
            if let img = img { self?.cache.setObject(img, forKey: uri as NSString) }
            DispatchQueue.main.async { done(img, err) }
        }
        if uri.hasPrefix("http://") || uri.hasPrefix("https://") {
            guard let url = URL(string: uri) else { finish(nil, "bad url"); return }
            URLSession.shared.dataTask(with: url) { data, _, error in
                if let d = data, let img = UIImage(data: d) { finish(img, nil) }
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
            if let d = data, let img = UIImage(data: d) { finish(img, nil) } else { finish(nil, "cannot load \(uri.prefix(60))") }
        }
    }
}
