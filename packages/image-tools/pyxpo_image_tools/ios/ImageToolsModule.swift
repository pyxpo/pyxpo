import Foundation
import UIKit
import ImageIO

struct ImageToolsError: Error {
    let message: String
    init(_ message: String) { self.message = message }
}

/// Native side of `pyxpo_image_tools`. Heavy work runs on one serial queue; replies come back through the host.
final class ImageToolsModule: PxModule {
    static let moduleName = "ImageTools"
    static let queue = DispatchQueue(label: "pyxpo.imagetools")

    init() {}

    func call(_ ctx: PxModuleContext, _ method: String, _ args: [Any], _ reply: @escaping PxReply) {
        switch method {
        case "ping":
            run(reply) { "pong" }
        case "info":
            run(reply) { try ImageTools.info(try Self.str(args, 0)) }
        case "open":
            run(reply) { try ImageTools.open(try Self.str(args, 0), maxEdge: (args.count > 1 ? args[1] as? Int : nil) ?? 0) }
        case "render":
            run(reply) {
                guard args.count > 1, let h = args[0] as? Int, let spec = args[1] as? [String: Any] else { throw ImageToolsError("render: bad arguments") }
                return try ImageTools.render(h, spec)
            }
        case "close":
            run(reply) {
                if let h = args.first as? Int { ImageTools.handles[h] = nil }
                return nil
            }
        default:
            reply(nil, "unknown native call ImageTools.\(method)")
        }
    }

    static func str(_ args: [Any], _ i: Int) throws -> String {
        guard i < args.count, let s = args[i] as? String else { throw ImageToolsError("missing string argument \(i)") }
        return s
    }

    /// Accepts a plain path or a file:// URL.
    static func path(_ uri: String) -> String {
        uri.hasPrefix("file://") ? (URL(string: uri)?.path ?? String(uri.dropFirst(7))) : uri
    }

    private func run(_ reply: @escaping PxReply, _ work: @escaping () throws -> Any?) {
        Self.queue.async {
            var value: Any?
            var message: String?
            do { value = try work() }
            catch let e as ImageToolsError { message = e.message }
            catch { message = "\(error)" }
            reply(value, message)
        }
    }
}

/// Decode with ImageIO (orientation baked in), crop/resize with CoreGraphics, encode with ImageIO. Encoding adds no
/// metadata properties, so output never carries EXIF/GPS. All state is touched on `ImageToolsModule.queue` only.
enum ImageTools {
    final class Handle {
        let image: CGImage
        let format: String
        init(_ image: CGImage, _ format: String) { self.image = image; self.format = format }
    }

    static var handles: [Int: Handle] = [:]
    static var nextHandle = 1

    static func source(_ uri: String) throws -> CGImageSource {
        let url = URL(fileURLWithPath: ImageToolsModule.path(uri))
        guard let src = CGImageSourceCreateWithURL(url as CFURL, nil), CGImageSourceGetCount(src) > 0 else {
            throw ImageToolsError("cannot read image: \(url.lastPathComponent)")
        }
        return src
    }

    static func formatName(_ src: CGImageSource) -> String {
        switch (CGImageSourceGetType(src) as String?) ?? "" {
        case "public.jpeg": return "jpeg"
        case "public.png": return "png"
        case "public.heic", "public.heif": return "heic"
        case "com.compuserve.gif": return "gif"
        case "org.webmproject.webp": return "webp"
        default: return "other"
        }
    }

    static func mime(_ format: String) -> String {
        format == "other" ? "application/octet-stream" : "image/" + format
    }

    /// Pixel size after EXIF orientation (orientations 5-8 swap width and height).
    static func orientedSize(_ props: [CFString: Any]) -> (Int, Int) {
        let w = props[kCGImagePropertyPixelWidth] as? Int ?? 0
        let h = props[kCGImagePropertyPixelHeight] as? Int ?? 0
        let o = props[kCGImagePropertyOrientation] as? Int ?? 1
        return o >= 5 && o <= 8 ? (h, w) : (w, h)
    }

    static func info(_ uri: String) throws -> [String: Any] {
        let src = try source(uri)
        let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any] ?? [:]
        let (w, h) = orientedSize(props)
        let p = ImageToolsModule.path(uri)
        let size = (try? FileManager.default.attributesOfItem(atPath: p)[.size] as? Int) ?? 0
        let format = formatName(src)
        let gps = props[kCGImagePropertyGPSDictionary] as? [CFString: Any]
        let exif = props[kCGImagePropertyExifDictionary] as? [CFString: Any]
        let tiff = props[kCGImagePropertyTIFFDictionary] as? [CFString: Any]
        return ["uri": p, "width": w, "height": h, "fileSize": size, "format": format, "mimeType": mime(format),
                "hasExif": (exif?.isEmpty == false) || (tiff?.isEmpty == false), "hasGps": gps?.isEmpty == false]
    }

    static func open(_ uri: String, maxEdge: Int) throws -> [String: Any] {
        let src = try source(uri)
        let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any] ?? [:]
        let (sw, sh) = orientedSize(props)
        let cap = maxEdge > 0 ? min(maxEdge, max(sw, sh)) : max(sw, sh)
        let opts: [CFString: Any] = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceThumbnailMaxPixelSize: cap,
            kCGImageSourceShouldCacheImmediately: true,
        ]
        guard let img = CGImageSourceCreateThumbnailAtIndex(src, 0, opts as CFDictionary) else {
            throw ImageToolsError("cannot decode image")
        }
        let h = nextHandle
        nextHandle += 1
        handles[h] = Handle(img, formatName(src))
        return ["h": h, "width": img.width, "height": img.height, "sourceWidth": sw, "sourceHeight": sh]
    }

    static func int(_ v: Any?) -> Int? {
        if let i = v as? Int { return i }
        if let d = v as? Double { return Int(d.rounded()) }
        return nil
    }

    static func render(_ h: Int, _ spec: [String: Any]) throws -> [String: Any] {
        guard let handle = handles[h] else { throw ImageToolsError("image handle closed") }
        var img = handle.image
        if let c = spec["crop"] as? [String: Any], let x = int(c["x"]), let y = int(c["y"]), let w = int(c["width"]), let ht = int(c["height"]) {
            let r = CGRect(x: x, y: y, width: w, height: ht).intersection(CGRect(x: 0, y: 0, width: img.width, height: img.height))
            guard !r.isEmpty, let cropped = img.cropping(to: r) else { throw ImageToolsError("crop outside image") }
            img = cropped
        }
        var format = (spec["format"] as? String) ?? "same"
        if format == "same" { format = ["jpeg", "png", "heic"].contains(handle.format) ? handle.format : "jpeg" }
        let uti: String
        switch format {
        case "jpeg": uti = "public.jpeg"
        case "png": uti = "public.png"
        case "heic": uti = "public.heic"
        default: throw ImageToolsError("unsupported output format \(format)")
        }
        let tw = int(spec["width"]) ?? img.width
        let th = int(spec["height"]) ?? img.height
        if tw < 1 || th < 1 || tw > 16384 || th > 16384 { throw ImageToolsError("bad output size \(tw)x\(th)") }
        // Redraw when resizing, or when JPEG must flatten alpha (JPEG has no alpha channel).
        let flatten = format != "png" && img.alphaInfo != .none && img.alphaInfo != .noneSkipFirst && img.alphaInfo != .noneSkipLast
        if tw != img.width || th != img.height || flatten {
            let noAlpha = format != "png"
            let info = noAlpha ? CGImageAlphaInfo.noneSkipLast.rawValue : CGImageAlphaInfo.premultipliedLast.rawValue
            guard let ctx = CGContext(data: nil, width: tw, height: th, bitsPerComponent: 8, bytesPerRow: 0,
                                      space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: info) else {
                throw ImageToolsError("out of memory resizing to \(tw)x\(th)")
            }
            if noAlpha { ctx.setFillColor(UIColor.white.cgColor); ctx.fill(CGRect(x: 0, y: 0, width: tw, height: th)) }
            ctx.interpolationQuality = .high
            ctx.draw(img, in: CGRect(x: 0, y: 0, width: tw, height: th))
            guard let out = ctx.makeImage() else { throw ImageToolsError("resize failed") }
            img = out
        }
        let dir = try outputDir()
        let ext = format == "jpeg" ? "jpg" : format
        let url = dir.appendingPathComponent(UUID().uuidString + "." + ext)
        guard let dest = CGImageDestinationCreateWithURL(url as CFURL, uti as CFString, 1, nil) else {
            throw ImageToolsError("\(format) encoding is not available")
        }
        var props: [CFString: Any] = [:]
        if format != "png" { props[kCGImageDestinationLossyCompressionQuality] = min(1.0, max(0.0, (spec["quality"] as? Double) ?? 0.9)) }
        CGImageDestinationAddImage(dest, img, props as CFDictionary)
        guard CGImageDestinationFinalize(dest) else { throw ImageToolsError("encoding failed") }
        let size = (try? FileManager.default.attributesOfItem(atPath: url.path)[.size] as? Int) ?? 0
        return ["uri": url.path, "fileSize": size, "width": img.width, "height": img.height, "format": format, "mimeType": mime(format)]
    }

    static func outputDir() throws -> URL {
        let base = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0].appendingPathComponent("pyxpo-images")
        try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        return base
    }
}
