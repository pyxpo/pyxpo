import UIKit

/// pyxpo-whiteboard on iOS: a Core Graphics view (`PxWhiteboard`) with pen, marker, eraser, fill bucket and
/// shapes, undo, redo and image export. The committed drawing is a bitmap context at screen scale; the element
/// under the finger is drawn on top of it.
final class WhiteboardModule: PxViewModule {
    static let moduleName = "Whiteboard"
    static let viewTypes = ["PxWhiteboard"]

    required init() {}

    func makeView(_ ctx: PxModuleContext, _ type: String, _ emit: @escaping (String, Any?) -> Void) -> PxNativeView {
        PxWhiteboardView(emit)
    }

    func call(_ ctx: PxModuleContext, _ method: String, _ args: [Any], _ reply: @escaping PxReply) {
        DispatchQueue.main.async {
            guard let tag = (args.first as? NSNumber)?.intValue, let v = ctx.view(tag) as? PxWhiteboardView else {
                reply(nil, "The Whiteboard is not mounted")
                return
            }
            switch method {
            case "undo": v.board.undo(); reply(nil, nil)
            case "redo": v.board.redo(); reply(nil, nil)
            case "clear": v.board.clear(); reply(nil, nil)
            case "getElements": reply(v.board.elements.map { $0.json }, nil)
            case "setElements":
                let list = args.count > 1 ? args[1] as? [[String: Any]] ?? [] : []
                v.board.setElements(list.compactMap(WBElement.init(json:)))
                reply(nil, nil)
            case "toImage":
                v.board.toImage(args.count > 1 ? args[1] as? [String: Any] ?? [:] : [:], reply)
            default:
                reply(nil, "Whiteboard has no method \(method)")
            }
        }
    }
}

private func wbColor(_ v: UInt32) -> CGColor {
    UIColor(red: CGFloat((v >> 16) & 255) / 255, green: CGFloat((v >> 8) & 255) / 255, blue: CGFloat(v & 255) / 255,
            alpha: CGFloat((v >> 24) & 255) / 255).cgColor
}

private func num(_ v: Any?) -> CGFloat? { (v as? NSNumber).map { CGFloat($0.doubleValue) } }

/// One stroke, shape or fill. A fill keeps its point in x0, y0.
struct WBElement {
    var type: String
    var tool = "pen"
    var shape = ""
    var color: UInt32
    var width: CGFloat = 0
    var fill: UInt32 = 0
    var points: [CGFloat] = []
    var x0: CGFloat = 0, y0: CGFloat = 0, x1: CGFloat = 0, y1: CGFloat = 0

    static let shapes: Set<String> = ["line", "arrow", "rect", "ellipse", "triangle", "star"]

    init(type: String, color: UInt32) { (self.type, self.color) = (type, color) }

    init?(json: [String: Any]) {
        let t = json["type"] as? String ?? "stroke"
        self.init(type: t, color: (json["color"] as? NSNumber)?.uint32Value ?? 0xFF000000)
        switch t {
        case "stroke":
            guard let pts = json["points"] as? [NSNumber], !pts.isEmpty, pts.count % 2 == 0 else { return nil }
            tool = json["tool"] as? String ?? "pen"
            width = num(json["width"]) ?? 4
            points = pts.map { CGFloat($0.doubleValue) }
        case "shape":
            guard let s = json["shape"] as? String, Self.shapes.contains(s), let a = num(json["x0"]), let b = num(json["y0"]),
                  let c = num(json["x1"]), let d = num(json["y1"]) else { return nil }
            shape = s
            width = num(json["width"]) ?? 4
            fill = (json["fill"] as? NSNumber)?.uint32Value ?? 0
            (x0, y0, x1, y1) = (a, b, c, d)
        case "fill":
            guard let a = num(json["x"]), let b = num(json["y"]) else { return nil }
            (x0, y0) = (a, b)
        default:
            return nil
        }
    }

    var json: [String: Any] {
        switch type {
        case "stroke":
            return ["type": "stroke", "tool": tool, "color": Int(color), "width": Double(width), "points": points.map { Double($0) }]
        case "shape":
            return ["type": "shape", "shape": shape, "color": Int(color), "width": Double(width), "fill": Int(fill),
                    "x0": Double(x0), "y0": Double(y0), "x1": Double(x1), "y1": Double(y1)]
        default:
            return ["type": "fill", "x": Double(x0), "y": Double(y0), "color": Int(color)]
        }
    }

    /// Draws a stroke or a shape (a fill is `flood`).
    func draw(_ c: CGContext, _ k: CGFloat) {
        c.saveGState()
        defer { c.restoreGState() }
        c.setLineCap(.round)
        c.setLineJoin(.round)
        if type == "shape" {
            let closed = path(c, k)
            if closed && fill >> 24 != 0 {
                c.setFillColor(wbColor(fill))
                if width > 0 { c.drawPath(using: .fill); _ = path(c, k) } else { c.fillPath() }
            }
            if width > 0 {
                c.setStrokeColor(wbColor(color))
                c.setLineWidth(width * k)
                c.strokePath()
            }
            c.beginPath()
            return
        }
        // Same curve on every platform: quadratic segments through the midpoints, a dot for a single point.
        c.setBlendMode(tool == "eraser" ? .clear : .normal)
        let ui = wbColor(tool == "eraser" ? 0xFF000000 : color)
        c.setStrokeColor(ui)
        c.setFillColor(ui)
        let n = points.count / 2
        if n == 1 {
            let r = width * k / 2
            c.fillEllipse(in: CGRect(x: points[0] * k - r, y: points[1] * k - r, width: 2 * r, height: 2 * r))
        } else if n > 1 {
            c.setLineWidth(width * k)
            c.move(to: CGPoint(x: points[0] * k, y: points[1] * k))
            for i in 1..<(n - 1) {
                c.addQuadCurve(to: CGPoint(x: (points[2 * i] + points[2 * i + 2]) / 2 * k, y: (points[2 * i + 1] + points[2 * i + 3]) / 2 * k),
                               control: CGPoint(x: points[2 * i] * k, y: points[2 * i + 1] * k))
            }
            c.addLine(to: CGPoint(x: points[2 * n - 2] * k, y: points[2 * n - 1] * k))
            c.strokePath()
        }
    }

    /// Arrow head line end: 28 degrees off the shaft, max(12, 3.5 x width) long, at most half the shaft.
    private func arrowHead(_ side: CGFloat) -> CGPoint {
        let dx = x1 - x0, dy = y1 - y0
        let n = max(hypot(dx, dy), 1e-9)
        let size = min(max(12, width * 3.5), n * 0.5)
        let a = atan2(dy, dx) + .pi + side * 28 * .pi / 180
        return CGPoint(x: x1 + size * cos(a), y: y1 + size * sin(a))
    }

    /// Adds the shape's path; true when it is closed (can be filled).
    private func path(_ c: CGContext, _ k: CGFloat) -> Bool {
        let lx = min(x0, x1), ly = min(y0, y1), hx = max(x0, x1), hy = max(y0, y1)
        let cx = (lx + hx) / 2, cy = (ly + hy) / 2, rx = (hx - lx) / 2, ry = (hy - ly) / 2
        func p(_ x: CGFloat, _ y: CGFloat) -> CGPoint { CGPoint(x: x * k, y: y * k) }
        c.beginPath()
        switch shape {
        case "line", "arrow":
            c.move(to: p(x0, y0))
            c.addLine(to: p(x1, y1))
            if shape == "arrow" {
                for side: CGFloat in [-1, 1] {
                    let h = arrowHead(side)
                    c.move(to: p(x1, y1))
                    c.addLine(to: p(h.x, h.y))
                }
            }
            return false
        case "rect":
            c.addRect(CGRect(x: lx * k, y: ly * k, width: (hx - lx) * k, height: (hy - ly) * k))
        case "ellipse":
            c.addEllipse(in: CGRect(x: lx * k, y: ly * k, width: (hx - lx) * k, height: (hy - ly) * k))
        case "triangle":
            c.move(to: p(cx, ly))
            c.addLine(to: p(hx, hy))
            c.addLine(to: p(lx, hy))
            c.closePath()
        default:  // star
            for j in 0..<10 {
                let a = -CGFloat.pi / 2 + .pi * CGFloat(j) / 5, r: CGFloat = j % 2 == 0 ? 1 : 0.45
                let q = p(cx + rx * r * cos(a), cy + ry * r * sin(a))
                if j == 0 { c.move(to: q) } else { c.addLine(to: q) }
            }
            c.closePath()
        }
        return true
    }

    /// Bucket fill on a flipped premultiplied RGBA bitmap context (memory rows from the top): the 4-connected
    /// region within `tol` of the tapped pixel gets the fill color, and the 1px ring around it gets the fill under
    /// its own color so the fill meets anti-aliased lines without a gap. False when nothing would change.
    static func flood(_ c: CGContext, _ e: WBElement, _ k: CGFloat, _ tol: Int) -> Bool {
        let w = c.width, h = c.height, bpr = c.bytesPerRow
        let sx = Int(floor(e.x0 * k)), sy = Int(floor(e.y0 * k))
        guard sx >= 0, sy >= 0, sx < w, sy < h, let d = c.data?.assumingMemoryBound(to: UInt8.self) else { return false }
        let fa = Int((e.color >> 24) & 255)
        let fr = Int((e.color >> 16) & 255) * fa / 255, fg = Int((e.color >> 8) & 255) * fa / 255, fb = Int(e.color & 255) * fa / 255
        let s = d + sy * bpr + sx * 4
        let s0 = Int(s[0]), s1 = Int(s[1]), s2 = Int(s[2]), s3 = Int(s[3])
        if abs(fr - s0) <= 2 && abs(fg - s1) <= 2 && abs(fb - s2) <= 2 && abs(fa - s3) <= 2 { return false }
        let mask = UnsafeMutablePointer<UInt8>.allocate(capacity: w * h)  // 1 region, 2 ring
        mask.initialize(repeating: 0, count: w * h)
        defer { mask.deallocate() }
        func match(_ x: Int, _ y: Int) -> Bool {
            if mask[y * w + x] == 1 { return false }
            let q = d + y * bpr + x * 4
            return abs(Int(q[0]) - s0) <= tol && abs(Int(q[1]) - s1) <= tol && abs(Int(q[2]) - s2) <= tol && abs(Int(q[3]) - s3) <= tol
        }
        var stack = [sx, sy]
        while let y = stack.popLast(), let x0 = stack.popLast() {
            guard match(x0, y) else { continue }
            var x = x0
            while x > 0 && match(x - 1, y) { x -= 1 }
            var up = false, down = false
            while x < w && match(x, y) {
                mask[y * w + x] = 1
                if y > 0 {
                    let m = match(x, y - 1)
                    if m && !up { stack.append(x); stack.append(y - 1) }
                    up = m
                }
                if y < h - 1 {
                    let m = match(x, y + 1)
                    if m && !down { stack.append(x); stack.append(y + 1) }
                    down = m
                }
                x += 1
            }
        }
        for y in 0..<h {
            for x in 0..<w where mask[y * w + x] == 0 {
                let i = y * w + x
                if (x > 0 && mask[i - 1] == 1) || (x < w - 1 && mask[i + 1] == 1) || (y > 0 && mask[i - w] == 1) || (y < h - 1 && mask[i + w] == 1) {
                    mask[i] = 2
                }
            }
        }
        for y in 0..<h {
            let row = d + y * bpr
            for x in 0..<w {
                let m = mask[y * w + x]
                if m == 0 { continue }
                let q = row + x * 4
                if m == 1 {
                    q[0] = UInt8(fr); q[1] = UInt8(fg); q[2] = UInt8(fb); q[3] = UInt8(fa)
                } else {  // existing over fill
                    let inv = 255 - Int(q[3])
                    q[0] = UInt8(min(255, Int(q[0]) + fr * inv / 255)); q[1] = UInt8(min(255, Int(q[1]) + fg * inv / 255))
                    q[2] = UInt8(min(255, Int(q[2]) + fb * inv / 255)); q[3] = UInt8(min(255, Int(q[3]) + fa * inv / 255))
                }
            }
        }
        return true
    }

    /// Draws any element on a flipped bitmap context; false when a fill changed nothing.
    func render(_ c: CGContext, _ k: CGFloat, _ tol: Int) -> Bool {
        if type == "fill" { return Self.flood(c, self, k, tol) }
        draw(c, k)
        return true
    }
}

/// A premultiplied RGBA bitmap context with its origin at the top left, like UIKit.
private func wbBitmap(_ w: Int, _ h: Int) -> CGContext? {
    guard let c = CGContext(data: nil, width: max(1, w), height: max(1, h), bitsPerComponent: 8, bytesPerRow: max(1, w) * 4,
                            space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return nil }
    c.translateBy(x: 0, y: CGFloat(max(1, h)))
    c.scaleBy(x: 1, y: -1)
    return c
}

final class PxWhiteboardView: PxNativeView {
    let board: PxBoardView
    var view: UIView { board }

    init(_ emit: @escaping (String, Any?) -> Void) { board = PxBoardView(emit) }

    func update(_ props: [String: Any], _ removed: [String]) {
        if let t = props["tool"] as? String { board.tool = t }
        if let c = props["color"] as? NSNumber { board.color = c.uint32Value }
        if let w = props["width"] as? NSNumber { board.lineWidth = CGFloat(w.doubleValue) }
        if let f = props["fill_color"] as? NSNumber { board.fillColor = f.uint32Value }
        if let e = props["enabled"] as? Bool { board.isUserInteractionEnabled = e }
        if let t = props["fill_tolerance"] as? NSNumber { board.setTolerance(t.intValue) }
        if let b = props["background_color"] as? NSNumber {
            board.background = b.uint32Value
            board.backgroundColor = UIColor(cgColor: wbColor(b.uint32Value))
        }
    }
}

final class PxBoardView: UIView {
    private enum Op { case add(WBElement), clear([WBElement]) }

    private let emit: (String, Any?) -> Void
    private(set) var elements: [WBElement] = []
    private var history: [Op] = []
    private var future: [Op] = []
    private var live: WBElement?
    private weak var touch: UITouch?
    private var done: CGContext?
    private var doneImage: UIImage?
    private var doneScale: CGFloat = 0
    var tool = "pen"
    var color: UInt32 = 0xFF000000
    var lineWidth: CGFloat = 4
    var fillColor: UInt32 = 0
    var background: UInt32 = 0xFFFFFFFF
    private var tolerance = 32

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

    private var scale: CGFloat { window?.screen.scale ?? UIScreen.main.scale }

    override func layoutSubviews() {
        super.layoutSubviews()
        let k = scale
        if done == nil || done!.width != Int((bounds.width * k).rounded()) || done!.height != Int((bounds.height * k).rounded()) || doneScale != k {
            rebuild()
        }
    }

    func setTolerance(_ t: Int) {
        guard t != tolerance else { return }
        tolerance = t
        if elements.contains(where: { $0.type == "fill" }) { rebuild() }
    }

    private func state() {
        emit("change", ["element_count": elements.count, "can_undo": !history.isEmpty, "can_redo": !future.isEmpty])
    }

    private func rebuild() {
        let k = scale
        let w = Int((bounds.width * k).rounded()), h = Int((bounds.height * k).rounded())
        doneScale = k
        doneImage = nil
        done = w > 0 && h > 0 ? wbBitmap(w, h) : nil
        if let c = done { for e in elements { _ = e.render(c, k, tolerance) } }
        setNeedsDisplay()
    }

    private func commit(_ e: WBElement) -> Bool {
        if done == nil { rebuild() }
        guard let c = done, e.render(c, doneScale, tolerance) else { return false }
        doneImage = nil
        elements.append(e)
        history.append(.add(e))
        future.removeAll()
        return true
    }

    override func draw(_ rect: CGRect) {
        guard let c = UIGraphicsGetCurrentContext() else { return }
        if doneImage == nil, let img = done?.makeImage() { doneImage = UIImage(cgImage: img, scale: doneScale, orientation: .up) }
        doneImage?.draw(in: bounds)
        live?.draw(c, 1)
    }

    // touches

    private func point(_ t: UITouch) -> (CGFloat, CGFloat) {
        let p = t.location(in: self)
        return ((p.x * 10).rounded() / 10, (p.y * 10).rounded() / 10)
    }

    private func add(_ t: UITouch, _ event: UIEvent?) {
        guard live != nil else { return }
        if live!.type == "shape" {
            (live!.x1, live!.y1) = point(t)
        } else {
            for one in event?.coalescedTouches(for: t) ?? [t] {
                let (x, y) = point(one)
                let n = live!.points.count
                if n > 0, abs(live!.points[n - 2] - x) < 0.5, abs(live!.points[n - 1] - y) < 0.5 { continue }
                live!.points.append(contentsOf: [x, y])
            }
        }
        setNeedsDisplay()
    }

    override func touchesBegan(_ touches: Set<UITouch>, with event: UIEvent?) {
        guard touch == nil, let t = touches.first else { return }
        emit("draw_start", ["tool": tool])
        let (x, y) = point(t)
        if tool == "fill" {
            var e = WBElement(type: "fill", color: color)
            (e.x0, e.y0) = (x, y)
            _ = commit(e)
            setNeedsDisplay()
            state()
            return
        }
        touch = t
        if WBElement.shapes.contains(tool) {
            var e = WBElement(type: "shape", color: color)
            e.shape = tool
            e.width = lineWidth
            e.fill = fillColor
            (e.x0, e.y0, e.x1, e.y1) = (x, y, x, y)
            live = e
        } else {
            var e = WBElement(type: "stroke", color: color)
            e.tool = tool
            e.width = lineWidth
            live = e
        }
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
        if keep, let e = live {
            let big = e.type != "shape" || abs(e.x1 - e.x0) >= 2 || abs(e.y1 - e.y0) >= 2
            if big && (e.type == "shape" || !e.points.isEmpty) { _ = commit(e) }
        }
        live = nil
        setNeedsDisplay()
        state()
    }

    // commands

    func undo() {
        guard let op = history.popLast() else { return }
        switch op {
        case .add: elements.removeLast()
        case .clear(let old): elements = old
        }
        future.append(op)
        rebuild()
        state()
    }

    func redo() {
        guard let op = future.popLast() else { return }
        switch op {
        case .add(let e): elements.append(e)
        case .clear: elements = []
        }
        history.append(op)
        rebuild()
        state()
    }

    func clear() {
        guard !elements.isEmpty else { return }
        history.append(.clear(elements))
        future.removeAll()
        elements = []
        rebuild()
        state()
    }

    func setElements(_ list: [WBElement]) {
        elements = list
        history.removeAll()
        future.removeAll()
        rebuild()
        state()
    }

    /// Renders the elements again at `scale` off the main thread, finds the ink, crops and writes the file.
    func toImage(_ o: [String: Any], _ reply: @escaping PxReply) {
        let k = CGFloat((o["scale"] as? NSNumber)?.doubleValue ?? Double(scale))
        let (list, size, bg, tol) = (elements, bounds.size, background, tolerance)
        let jpg = (o["format"] as? String) == "jpg"
        let trim = o["trim"] as? Bool ?? false
        let pad = CGFloat((o["padding"] as? NSNumber)?.doubleValue ?? 0)
        let withBackground = o["background"] as? Bool ?? true
        let quality = CGFloat((o["quality"] as? NSNumber)?.doubleValue ?? 1)
        DispatchQueue.global(qos: .userInitiated).async {
            let w = max(1, Int((size.width * k).rounded())), h = max(1, Int((size.height * k).rounded()))
            guard let ink = wbBitmap(w, h) else { reply(nil, "Could not make the image"); return }
            for e in list { _ = e.render(ink, k, tol) }
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
                if withBackground { UIColor(cgColor: wbColor(bg)).setFill(); ctx.fill(CGRect(origin: .zero, size: r.size)) }
                UIImage(cgImage: inkImage).draw(at: CGPoint(x: -r.minX, y: -r.minY))
            }
            guard let data = jpg ? image.jpegData(compressionQuality: quality) : image.pngData() else {
                reply(nil, "Could not encode the image"); return
            }
            do {
                let dir = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
                    .appendingPathComponent("Whiteboard")
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
