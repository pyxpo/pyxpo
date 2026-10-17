import UIKit

/// pyxpo-drawing-canvas on iOS: a Core Graphics view (`PxDrawingCanvas`) with undo, redo and image export.
final class DrawingCanvasModule: PxViewModule {
    static let moduleName = "DrawingCanvas"
    static let viewTypes = ["PxDrawingCanvas"]

    required init() {}

    func makeView(_ ctx: PxModuleContext, _ type: String, _ emit: @escaping (String, Any?) -> Void) -> PxNativeView {
        PxDrawingCanvasView(emit)
    }

    func call(_ ctx: PxModuleContext, _ method: String, _ args: [Any], _ reply: @escaping PxReply) {
        DispatchQueue.main.async {
            guard let tag = (args.first as? NSNumber)?.intValue, let v = ctx.view(tag) as? PxDrawingCanvasView else {
                reply(nil, "The DrawingCanvas is not mounted")
                return
            }
            switch method {
            case "undo": v.canvas.undo(); reply(nil, nil)
            case "redo": v.canvas.redo(); reply(nil, nil)
            case "clear": v.canvas.clear(); reply(nil, nil)
            case "getStrokes": reply(v.canvas.strokes.map { $0.json }, nil)
            case "setStrokes":
                let list = args.count > 1 ? args[1] as? [[String: Any]] ?? [] : []
                v.canvas.setStrokes(list.compactMap(Stroke.init(json:)))
                reply(nil, nil)
            case "toImage":
                v.canvas.toImage(args.count > 1 ? args[1] as? [String: Any] ?? [:] : [:], reply)
            default:
                reply(nil, "DrawingCanvas has no method \(method)")
            }
        }
    }
}

struct Stroke {
    var tool: String
    var color: UInt32
    var width: CGFloat
    var points: [CGFloat]

    init(tool: String, color: UInt32, width: CGFloat, points: [CGFloat] = []) {
        (self.tool, self.color, self.width, self.points) = (tool, color, width, points)
    }

    init?(json: [String: Any]) {
        guard let pts = json["points"] as? [NSNumber], !pts.isEmpty, pts.count % 2 == 0 else { return nil }
        self.init(tool: json["tool"] as? String ?? "pen", color: (json["color"] as? NSNumber)?.uint32Value ?? 0xFF000000,
                  width: CGFloat((json["width"] as? NSNumber)?.doubleValue ?? 4), points: pts.map { CGFloat($0.doubleValue) })
    }

    var json: [String: Any] {
        ["tool": tool, "color": Int(color), "width": Double(width), "points": points.map { Double($0) }]
    }

    /// Same curve on every platform: quadratic segments through the midpoints, a dot for a single point.
    func draw(_ c: CGContext, _ k: CGFloat) {
        c.saveGState()
        c.setBlendMode(tool == "eraser" ? .clear : .normal)
        let ui = argb(color)
        c.setStrokeColor(ui.cgColor)
        c.setFillColor(ui.cgColor)
        let n = points.count / 2
        if n == 1 {
            let r = width * k / 2
            c.fillEllipse(in: CGRect(x: points[0] * k - r, y: points[1] * k - r, width: 2 * r, height: 2 * r))
        } else if n > 1 {
            c.setLineWidth(width * k)
            c.setLineCap(.round)
            c.setLineJoin(.round)
            c.move(to: CGPoint(x: points[0] * k, y: points[1] * k))
            for i in 1..<(n - 1) {
                c.addQuadCurve(to: CGPoint(x: (points[2 * i] + points[2 * i + 2]) / 2 * k, y: (points[2 * i + 1] + points[2 * i + 3]) / 2 * k),
                               control: CGPoint(x: points[2 * i] * k, y: points[2 * i + 1] * k))
            }
            c.addLine(to: CGPoint(x: points[2 * n - 2] * k, y: points[2 * n - 1] * k))
            c.strokePath()
        }
        c.restoreGState()
    }
}

func argb(_ v: UInt32) -> UIColor {
    UIColor(red: CGFloat((v >> 16) & 255) / 255, green: CGFloat((v >> 8) & 255) / 255, blue: CGFloat(v & 255) / 255,
            alpha: CGFloat((v >> 24) & 255) / 255)
}

final class PxDrawingCanvasView: PxNativeView {
    let canvas: PxCanvasView
    var view: UIView { canvas }

    init(_ emit: @escaping (String, Any?) -> Void) { canvas = PxCanvasView(emit) }

    func update(_ props: [String: Any], _ removed: [String]) {
        if let c = props["stroke_color"] as? NSNumber { canvas.strokeColor = c.uint32Value }
        if let w = props["stroke_width"] as? NSNumber { canvas.strokeWidth = CGFloat(w.doubleValue) }
        if let t = props["tool"] as? String { canvas.tool = t }
        if let e = props["enabled"] as? Bool { canvas.isUserInteractionEnabled = e }
        if let b = props["background_color"] as? NSNumber {
            canvas.background = b.uint32Value
            canvas.backgroundColor = argb(b.uint32Value)
        }
    }
}

final class PxCanvasView: UIView {
    private enum Op { case stroke(Stroke), clear([Stroke]) }

    private let emit: (String, Any?) -> Void
    private(set) var strokes: [Stroke] = []
    private var history: [Op] = []
    private var future: [Op] = []
    private var live: Stroke?
    private weak var touch: UITouch?
    private var done: UIImage?
    var strokeColor: UInt32 = 0xFF000000
    var strokeWidth: CGFloat = 4
    var tool = "pen"
    var background: UInt32 = 0xFFFFFFFF

    init(_ emit: @escaping (String, Any?) -> Void) {
        self.emit = emit
        super.init(frame: .zero)
        isOpaque = false
        isMultipleTouchEnabled = false
        clipsToBounds = true
        contentMode = .redraw
        backgroundColor = .white
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }

    override func layoutSubviews() {
        super.layoutSubviews()
        if let d = done, d.size != bounds.size { rebuild() }
    }

    private func state() {
        emit("change", ["stroke_count": strokes.count, "can_undo": !history.isEmpty, "can_redo": !future.isEmpty])
    }

    private func rebuild() {
        let size = bounds.size
        done = size.width > 0 && size.height > 0 ? UIGraphicsImageRenderer(size: size).image { r in
            for s in strokes { s.draw(r.cgContext, 1) }
        } : nil
        setNeedsDisplay()
    }

    private func commit(_ s: Stroke) {
        let size = bounds.size
        guard size.width > 0, size.height > 0 else { return }
        let prev = done
        done = UIGraphicsImageRenderer(size: size).image { r in
            prev?.draw(at: .zero)
            s.draw(r.cgContext, 1)
        }
    }

    override func draw(_ rect: CGRect) {
        guard let c = UIGraphicsGetCurrentContext() else { return }
        done?.draw(at: .zero)
        live?.draw(c, 1)
    }

    // touches

    private func add(_ t: UITouch, _ event: UIEvent?) {
        let all = event?.coalescedTouches(for: t) ?? [t]
        for one in all {
            let p = one.location(in: self)
            let x = (p.x * 10).rounded() / 10, y = (p.y * 10).rounded() / 10
            if let n = live?.points.count, n > 0, abs(live!.points[n - 2] - x) < 0.5, abs(live!.points[n - 1] - y) < 0.5 { continue }
            live?.points.append(contentsOf: [x, y])
        }
        setNeedsDisplay()
    }

    override func touchesBegan(_ touches: Set<UITouch>, with event: UIEvent?) {
        guard touch == nil, let t = touches.first else { return }
        touch = t
        live = Stroke(tool: tool, color: strokeColor, width: strokeWidth)
        add(t, event)
    }

    override func touchesMoved(_ touches: Set<UITouch>, with event: UIEvent?) {
        if let t = touch, touches.contains(t) { add(t, event) }
    }

    override func touchesEnded(_ touches: Set<UITouch>, with event: UIEvent?) {
        guard let t = touch, touches.contains(t) else { return }
        add(t, event)
        finish(true)
    }

    override func touchesCancelled(_ touches: Set<UITouch>, with event: UIEvent?) {
        if let t = touch, touches.contains(t) { finish(false) }
    }

    private func finish(_ keep: Bool) {
        touch = nil
        if keep, let s = live, !s.points.isEmpty {
            strokes.append(s)
            history.append(.stroke(s))
            future.removeAll()
            commit(s)
            live = nil
            state()
        }
        live = nil
        setNeedsDisplay()
    }

    // commands

    func undo() {
        guard let op = history.popLast() else { return }
        switch op {
        case .stroke: strokes.removeLast()
        case .clear(let old): strokes = old
        }
        future.append(op)
        rebuild()
        state()
    }

    func redo() {
        guard let op = future.popLast() else { return }
        switch op {
        case .stroke(let s): strokes.append(s)
        case .clear: strokes = []
        }
        history.append(op)
        rebuild()
        state()
    }

    func clear() {
        guard !strokes.isEmpty else { return }
        history.append(.clear(strokes))
        future.removeAll()
        strokes = []
        rebuild()
        state()
    }

    func setStrokes(_ list: [Stroke]) {
        strokes = list
        history.removeAll()
        future.removeAll()
        rebuild()
        state()
    }

    /// Renders the strokes again at `scale` off the main thread, finds the ink, crops and writes the file.
    func toImage(_ o: [String: Any], _ reply: @escaping PxReply) {
        let k = CGFloat((o["scale"] as? NSNumber)?.doubleValue ?? Double(window?.screen.scale ?? UIScreen.main.scale))
        let (list, size, bg) = (strokes, bounds.size, background)
        let jpg = (o["format"] as? String) == "jpg"
        let trim = o["trim"] as? Bool ?? false
        let pad = CGFloat((o["padding"] as? NSNumber)?.doubleValue ?? 0)
        let withBackground = o["background"] as? Bool ?? true
        let quality = CGFloat((o["quality"] as? NSNumber)?.doubleValue ?? 1)
        DispatchQueue.global(qos: .userInitiated).async {
            let w = max(1, Int((size.width * k).rounded())), h = max(1, Int((size.height * k).rounded()))
            guard let ink = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4,
                                      space: CGColorSpaceCreateDeviceRGB(),
                                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
                reply(nil, "Could not make the image"); return
            }
            ink.translateBy(x: 0, y: CGFloat(h))
            ink.scaleBy(x: 1, y: -1)  // top left origin, like UIKit
            for s in list { s.draw(ink, k) }
            var r = CGRect(x: 0, y: 0, width: w, height: h)
            if trim {
                guard let b = Self.inkBounds(ink, w, h) else { reply(nil, nil); return }
                let p = (pad * k).rounded()
                r = b.insetBy(dx: -p, dy: -p)
            }
            guard let inkImage = ink.makeImage() else { reply(nil, "Could not make the image"); return }
            let format = UIGraphicsImageRendererFormat()
            format.scale = 1
            format.opaque = jpg
            let image = UIGraphicsImageRenderer(size: r.size, format: format).image { ctx in
                if jpg { UIColor.white.setFill(); ctx.fill(CGRect(origin: .zero, size: r.size)) }
                if withBackground { argb(bg).setFill(); ctx.fill(CGRect(origin: .zero, size: r.size)) }
                UIImage(cgImage: inkImage).draw(at: CGPoint(x: -r.minX, y: -r.minY))
            }
            guard let data = jpg ? image.jpegData(compressionQuality: quality) : image.pngData() else {
                reply(nil, "Could not encode the image"); return
            }
            do {
                let dir = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
                    .appendingPathComponent("DrawingCanvas")
                try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
                let url = dir.appendingPathComponent(UUID().uuidString + (jpg ? ".jpg" : ".png"))
                try data.write(to: url)
                reply(["uri": url.absoluteString, "width": Int(r.width), "height": Int(r.height),
                       "x": Double(r.minX / k), "y": Double(r.minY / k)], nil)
            } catch {
                reply(nil, error.localizedDescription)
            }
        }
    }

    /// Pixel rect of everything with alpha, rows from the top (the context is flipped).
    static func inkBounds(_ c: CGContext, _ w: Int, _ h: Int) -> CGRect? {
        guard let data = c.data?.assumingMemoryBound(to: UInt8.self) else { return nil }
        var x0 = w, y0 = h, x1 = -1, y1 = -1
        for y in 0..<h {
            let row = data + y * c.bytesPerRow
            for x in 0..<w where row[x * 4 + 3] != 0 {
                if x < x0 { x0 = x }
                if x > x1 { x1 = x }
                if y < y0 { y0 = y }
                if y > y1 { y1 = y }
            }
        }
        return x1 < 0 ? nil : CGRect(x: x0, y: y0, width: x1 - x0 + 1, height: y1 - y0 + 1)
    }
}
