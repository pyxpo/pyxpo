import UIKit

/// Container whose children are placed by OpApplier from engine frames. No auto layout, no layoutSubviews.
class PxGroup: UIView {
    /// Set when the view has on_press* handlers. Events: press_in(point), press_out, press, long_press.
    var onTouch: ((String, CGPoint?) -> Void)?
    /// Set for on_touch_start/move/end: (event name, point in view, point in window).
    var onRaw: ((String, CGPoint, CGPoint) -> Void)?
    private var down = false
    private var long = false
    private var timer: Timer?

    private func inside(_ t: UITouch) -> Bool { bounds.insetBy(dx: -24, dy: -24).contains(t.location(in: self)) }

    private func raw(_ name: String, _ touches: Set<UITouch>) {
        guard let r = onRaw, let t = touches.first else { return }
        r(name, t.location(in: self), t.location(in: nil))
    }

    override func touchesBegan(_ touches: Set<UITouch>, with event: UIEvent?) {
        raw("touch_start", touches)
        guard let cb = onTouch, let t = touches.first else { return onRaw != nil ? () : super.touchesBegan(touches, with: event) }
        down = true; long = false
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: false) { [weak self] _ in
            guard let self = self, self.down else { return }
            self.long = true; cb("long_press", nil)
        }
        cb("press_in", t.location(in: self))
    }

    override func touchesMoved(_ touches: Set<UITouch>, with event: UIEvent?) {
        raw("touch_move", touches)
        guard let cb = onTouch, let t = touches.first else { return onRaw != nil ? () : super.touchesMoved(touches, with: event) }
        if down && !inside(t) { down = false; timer?.invalidate(); cb("press_out", nil) }
    }

    override func touchesEnded(_ touches: Set<UITouch>, with event: UIEvent?) {
        raw("touch_end", touches)
        guard let cb = onTouch else { return onRaw != nil ? () : super.touchesEnded(touches, with: event) }
        timer?.invalidate()
        if down { down = false; cb("press_out", nil); if !long { cb("press", nil) } }
    }

    override func touchesCancelled(_ touches: Set<UITouch>, with event: UIEvent?) {
        raw("touch_end", touches)
        guard let cb = onTouch else { return onRaw != nil ? () : super.touchesCancelled(touches, with: event) }
        timer?.invalidate()
        if down { down = false; cb("press_out", nil) }
    }
}

/// Root view, pinned to the safe area. Reports size and trait changes.
final class PxRoot: UIView {
    var onSize: ((CGSize) -> Void)?
    var onTraits: (() -> Void)?

    override func layoutSubviews() {
        super.layoutSubviews()
        onSize?(bounds.size)
    }

    override func safeAreaInsetsDidChange() {
        super.safeAreaInsetsDidChange()
        onTraits?()
    }

    override func traitCollectionDidChange(_ previous: UITraitCollection?) {
        super.traitCollectionDidChange(previous)
        onTraits?()
    }
}

/// ScrollView host: `content` is placed by the engine's synthetic content node.
final class ScrollHost: UIScrollView, UIScrollViewDelegate {
    let content = PxGroup()
    var emit = false, onBegin = false, onEnd = false, onMomentum = false
    var horizontal = false  // set from the `horizontal` prop at create; used by scroll_to_end
    var throttle: TimeInterval = 0.016
    var ae: [String: Int]?
    var onAE: (([Int: Double]) -> Void)?
    var onEvent: ((String, [String: Any]) -> Void)?
    private var last: TimeInterval = 0

    override init(frame: CGRect) {
        super.init(frame: frame)
        contentInsetAdjustmentBehavior = .never
        delegate = self
        addSubview(content)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) not supported") }

    func info() -> [String: Any] {
        ["x": Double(contentOffset.x), "y": Double(contentOffset.y),
         "width": Double(bounds.width), "height": Double(bounds.height),
         "content_width": Double(contentSize.width), "content_height": Double(contentSize.height)]
    }

    private func send(_ name: String) { onEvent?(name, ["value": info()]) }

    func scrollViewDidScroll(_ s: UIScrollView) {
        if let m = ae, let b = onAE {
            let i = info()
            var vals: [Int: Double] = [:]
            for (k, id) in m { if let v = i[k] as? Double { vals[id] = v } }
            b(vals)
        }
        let now = CACurrentMediaTime()
        if emit && now - last >= throttle { last = now; send("scroll") }
    }

    func scrollViewWillBeginDragging(_ s: UIScrollView) { if onBegin { send("scroll_begin_drag") } }

    func scrollViewDidEndDragging(_ s: UIScrollView, willDecelerate d: Bool) {
        if onEnd { send("scroll_end_drag") }
        if !d { settled() }
    }

    func scrollViewDidEndDecelerating(_ s: UIScrollView) { settled() }
    func scrollViewDidEndScrollingAnimation(_ s: UIScrollView) { settled() }

    private func settled() {
        if emit { send("scroll") }
        if onMomentum { send("momentum_scroll_end") }
    }
}

/// Label that draws inside padding + border insets (the engine's frame includes them).
final class PxLabel: UILabel {
    var insets = UIEdgeInsets.zero
    /// Sublayers always draw above a label's own text, so the box is rendered here, before the text.
    var box: BoxLayer?

    override func drawText(in rect: CGRect) {
        if let b = box, let ctx = UIGraphicsGetCurrentContext() {
            ctx.saveGState()
            ctx.translateBy(x: 0, y: bounds.height)
            ctx.scaleBy(x: 1, y: -1)
            b.render(in: ctx)
            ctx.restoreGState()
        }
        super.drawText(in: rect.inset(by: insets))
    }
}

final class PxTextField: UITextField {
    var insets = UIEdgeInsets.zero
    var maxLength = 0
    var selectOnFocus = false

    override func becomeFirstResponder() -> Bool {
        let ok = super.becomeFirstResponder()
        if ok && selectOnFocus { DispatchQueue.main.async { self.selectAll(nil) } }
        return ok
    }

    override func textRect(forBounds bounds: CGRect) -> CGRect { bounds.inset(by: insets) }
    override func editingRect(forBounds bounds: CGRect) -> CGRect { bounds.inset(by: insets) }
    override func placeholderRect(forBounds bounds: CGRect) -> CGRect { bounds.inset(by: insets) }
}

/// What a box looks like. Sizes in pt. Radii order: top-left, top-right, bottom-right, bottom-left.
struct BoxSpec {
    var bg: UIColor?
    var gradAngle: CGFloat = 180
    var gradColors: [UIColor]?
    var gradStops: [CGFloat] = []
    var radii: [CGFloat] = [0, 0, 0, 0]
    var bw: [CGFloat] = [0, 0, 0, 0]          // border widths: left, top, right, bottom
    var bc: [UIColor] = Array(repeating: .black, count: 4)
    var clip = false

    var hasBox: Bool { bg != nil || gradColors != nil || radii.contains { $0 > 0 } || bw.contains { $0 > 0 } }
}

/// Draws background colour or linear gradient, per-corner radii and per-side borders as a layer under the view's own content.
final class BoxLayer: CALayer {
    private let fill = CAShapeLayer()
    private let gradient = CAGradientLayer()
    private let ring = CAShapeLayer()
    private let sides = CALayer()
    private let sidePolys = (0..<4).map { _ in CAShapeLayer() }
    private let sidesMask = CAShapeLayer()
    var spec = BoxSpec()

    override init() {
        super.init()
        zPosition = -1  // behind the owner layer's own contents (label text etc.)
        addSublayer(fill)
        addSublayer(gradient)
        ring.fillRule = .evenOdd
        addSublayer(ring)
        for p in sidePolys { sides.addSublayer(p) }
        sides.mask = sidesMask
        addSublayer(sides)
    }

    override init(layer: Any) { super.init(layer: layer) }
    required init?(coder: NSCoder) { fatalError("init(coder:) not supported") }

    static func rrect(_ r: CGRect, _ radii: [CGFloat]) -> UIBezierPath {
        var q = radii
        let k = min(1, r.width / max(1, max(q[0] + q[1], q[3] + q[2])), r.height / max(1, max(q[0] + q[3], q[1] + q[2])))
        if k < 1 { q = q.map { $0 * k } }
        let p = UIBezierPath()
        p.move(to: CGPoint(x: r.minX + q[0], y: r.minY))
        p.addLine(to: CGPoint(x: r.maxX - q[1], y: r.minY))
        if q[1] > 0 { p.addArc(withCenter: CGPoint(x: r.maxX - q[1], y: r.minY + q[1]), radius: q[1], startAngle: -.pi / 2, endAngle: 0, clockwise: true) }
        p.addLine(to: CGPoint(x: r.maxX, y: r.maxY - q[2]))
        if q[2] > 0 { p.addArc(withCenter: CGPoint(x: r.maxX - q[2], y: r.maxY - q[2]), radius: q[2], startAngle: 0, endAngle: .pi / 2, clockwise: true) }
        p.addLine(to: CGPoint(x: r.minX + q[3], y: r.maxY))
        if q[3] > 0 { p.addArc(withCenter: CGPoint(x: r.minX + q[3], y: r.maxY - q[3]), radius: q[3], startAngle: .pi / 2, endAngle: .pi, clockwise: true) }
        p.addLine(to: CGPoint(x: r.minX, y: r.minY + q[0]))
        if q[0] > 0 { p.addArc(withCenter: CGPoint(x: r.minX + q[0], y: r.minY + q[0]), radius: q[0], startAngle: .pi, endAngle: 3 * .pi / 2, clockwise: true) }
        p.close()
        return p
    }

    /// Outer shape path for the given bounds (also used for shadow and clipping).
    func outerPath(_ b: CGRect) -> UIBezierPath { Self.rrect(b, spec.radii) }

    func update(_ b: CGRect) {
        frame = b
        let r = CGRect(origin: .zero, size: b.size)
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        defer { CATransaction.commit() }
        let outer = outerPath(r)
        fill.path = outer.cgPath
        fill.fillColor = spec.gradColors == nil ? spec.bg?.cgColor : nil
        if let g = spec.gradColors {
            gradient.isHidden = false
            gradient.frame = r
            gradient.colors = g.map { $0.cgColor }
            gradient.locations = spec.gradStops.map { NSNumber(value: Double($0)) }
            let a = spec.gradAngle * .pi / 180
            let dx = sin(a), dy = -cos(a)
            let len = abs(r.width * dx) + abs(r.height * dy)
            let c = CGPoint(x: r.midX, y: r.midY)
            gradient.startPoint = CGPoint(x: (c.x - dx * len / 2) / max(1, r.width), y: (c.y - dy * len / 2) / max(1, r.height))
            gradient.endPoint = CGPoint(x: (c.x + dx * len / 2) / max(1, r.width), y: (c.y + dy * len / 2) / max(1, r.height))
            let m = CAShapeLayer(); m.path = outer.cgPath
            gradient.mask = m
        } else {
            gradient.isHidden = true
        }
        let bw = spec.bw
        guard bw.contains(where: { $0 > 0 }) else { ring.isHidden = true; sides.isHidden = true; return }
        let ir = CGRect(x: r.minX + bw[0], y: r.minY + bw[1], width: max(0, r.width - bw[0] - bw[2]), height: max(0, r.height - bw[1] - bw[3]))
        let q = spec.radii
        let ri = [max(0, q[0] - max(bw[0], bw[1])), max(0, q[1] - max(bw[2], bw[1])),
                  max(0, q[2] - max(bw[2], bw[3])), max(0, q[3] - max(bw[0], bw[3]))]
        let both = UIBezierPath(cgPath: outer.cgPath)
        both.append(Self.rrect(ir, ri))
        let uniform = spec.bc.allSatisfy { $0 == spec.bc[0] }
        if uniform {
            ring.isHidden = false; sides.isHidden = true
            ring.path = both.cgPath
            ring.fillColor = spec.bc[0].cgColor
        } else {
            ring.isHidden = true; sides.isHidden = false
            sides.frame = r
            sidesMask.path = both.cgPath
            sidesMask.fillRule = .evenOdd
            let l = r.minX, t = r.minY, rt = r.maxX, bt = r.maxY
            let polys: [[CGPoint]] = [
                [CGPoint(x: l, y: t), CGPoint(x: l, y: bt), CGPoint(x: l + bw[0], y: bt - bw[3]), CGPoint(x: l + bw[0], y: t + bw[1])],
                [CGPoint(x: l, y: t), CGPoint(x: rt, y: t), CGPoint(x: rt - bw[2], y: t + bw[1]), CGPoint(x: l + bw[0], y: t + bw[1])],
                [CGPoint(x: rt, y: t), CGPoint(x: rt, y: bt), CGPoint(x: rt - bw[2], y: bt - bw[3]), CGPoint(x: rt - bw[2], y: t + bw[1])],
                [CGPoint(x: l, y: bt), CGPoint(x: rt, y: bt), CGPoint(x: rt - bw[2], y: bt - bw[3]), CGPoint(x: l + bw[0], y: bt - bw[3])],
            ]
            for (i, pts) in polys.enumerated() {
                let p = UIBezierPath()
                p.move(to: pts[0]); for pt in pts.dropFirst() { p.addLine(to: pt) }; p.close()
                sidePolys[i].path = p.cgPath
                sidePolys[i].fillColor = spec.bc[i].cgColor
            }
        }
    }
}
