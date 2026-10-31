import UIKit

/// Container whose children are placed by OpApplier from engine frames. No auto layout, no layoutSubviews.
class PxGroup: UIView {
    /// Set when the view has on_press* handlers. Events: press_in(point), press_out, press, long_press.
    var onTouch: ((String, CGPoint?) -> Void)?
    /// Set for on_touch_start/move/end: (event name, point in view, point in window).
    var onRaw: ((String, CGPoint, CGPoint) -> Void)?
    /// React Native pointerEvents: "auto", "none" (no touches here or below), "box-none" (only children get
    /// touches; the rest fall through to what is behind), "box-only" (this view gets them, children do not).
    var pointerEvents = "auto"
    private var down = false
    private var long = false
    private var timer: Timer?

    override func hitTest(_ point: CGPoint, with event: UIEvent?) -> UIView? {
        switch pointerEvents {
        case "none": return nil
        case "box-none": let h = super.hitTest(point, with: event); return h === self ? nil : h
        case "box-only":
            guard !isHidden, isUserInteractionEnabled, alpha > 0.01, self.point(inside: point, with: event) else { return nil }
            return self
        default: return super.hitTest(point, with: event)
        }
    }

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

    /// RTL: a horizontal list starts at its right end. When the content grows, the part shown stays put relative
    /// to the right edge (content is mirrored inside it, so new items appear on the left).
    func keepRightEdge(was old: CGSize) {
        let fromRight = old.width > 0 ? max(0, old.width - bounds.width - contentOffset.x) : 0
        contentOffset.x = max(0, contentSize.width - bounds.width - fromRight)
    }

    /// Scrolls to where reading starts: the right end in RTL.
    func toStart(rtl: Bool) {
        contentOffset.x = rtl ? max(0, contentSize.width - bounds.width) : 0
    }

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

    #if targetEnvironment(macCatalyst)
    // In the Mac idiom a UIScrollView scrolls only with a trackpad or wheel; a mouse click-drag does nothing.
    // This pan adds click-drag scrolling with a short glide. Touches on controls, raw-touch views (a canvas)
    // and custom views that handle touches are left alone, and only a drag along the scroll axis starts it.
    private lazy var mouseDrag: UIPanGestureRecognizer = {
        let g = UIPanGestureRecognizer(target: self, action: #selector(dragged(_:)))
        g.allowedTouchTypes = [NSNumber(value: UITouch.TouchType.direct.rawValue),
                               NSNumber(value: UITouch.TouchType.indirectPointer.rawValue)]
        gate.host = self
        g.delegate = gate
        return g
    }()
    private let gate = DragGate()
    private var dragStart = CGPoint.zero

    override func didMoveToWindow() {
        super.didMoveToWindow()
        if window != nil, mouseDrag.view == nil { addGestureRecognizer(mouseDrag) }
    }

    private var maxOffset: CGPoint {
        CGPoint(x: max(0, contentSize.width - bounds.width), y: max(0, contentSize.height - bounds.height))
    }

    private func clamped(_ p: CGPoint) -> CGPoint {
        let m = maxOffset
        return CGPoint(x: min(max(p.x, 0), m.x), y: min(max(p.y, 0), m.y))
    }

    @objc private func dragged(_ g: UIPanGestureRecognizer) {
        let t = g.translation(in: self)
        switch g.state {
        case .began:
            setContentOffset(contentOffset, animated: false)  // stops a glide still running
            dragStart = contentOffset
            if onBegin { send("scroll_begin_drag") }
        case .changed:
            contentOffset = clamped(horizontal ? CGPoint(x: dragStart.x - t.x, y: dragStart.y)
                                               : CGPoint(x: dragStart.x, y: dragStart.y - t.y))
        case .ended, .cancelled:
            if onEnd { send("scroll_end_drag") }
            let v = g.state == .ended ? g.velocity(in: self) : .zero
            var target = clamped(horizontal ? CGPoint(x: contentOffset.x - v.x * 0.2, y: contentOffset.y)
                                            : CGPoint(x: contentOffset.x, y: contentOffset.y - v.y * 0.2))
            if isPagingEnabled, bounds.width > 0, bounds.height > 0 {
                target = clamped(horizontal ? CGPoint(x: (target.x / bounds.width).rounded() * bounds.width, y: target.y)
                                            : CGPoint(x: target.x, y: (target.y / bounds.height).rounded() * bounds.height))
            }
            if target == contentOffset { settled() } else { setContentOffset(target, animated: true) }
        default: break
        }
    }

    /// True when a touch on `v` belongs to that view (or one between it and this scroll view), not to a drag.
    private func ownsTouch(_ v: UIView?) -> Bool {
        var cur = v
        while let u = cur, u !== self {
            if u is UIControl || u is UITextView { return true }
            if let s = u as? ScrollHost, s.horizontal == horizontal, s.isScrollEnabled,
               (horizontal ? s.maxOffset.x : s.maxOffset.y) > 0 { return true }
            if let p = u as? PxGroup {
                if p.onRaw != nil { return true }
            } else if !(u is UIScrollView), Bundle(for: type(of: u)) == Bundle.main {
                // An app or module view (a canvas, a mesh view) that reads touches or has its own gestures.
                // Compared with its nearest UIKit class, so a label or image subclass still counts as passive.
                let sel = #selector(UIResponder.touchesBegan(_:with:))
                var base: AnyClass = type(of: u)
                while Bundle(for: base) == Bundle.main, let up = class_getSuperclass(base) { base = up }
                if class_getMethodImplementation(type(of: u), sel) != class_getMethodImplementation(base, sel) { return true }
                if !(u.gestureRecognizers ?? []).isEmpty { return true }
            }
            cur = u.superview
        }
        return false
    }

    fileprivate func dragMayReceive(_ t: UITouch) -> Bool { !ownsTouch(t.view) }

    fileprivate func dragMayBegin(_ g: UIGestureRecognizer) -> Bool {
        guard isScrollEnabled, let p = g as? UIPanGestureRecognizer else { return false }
        // The system pan already scrolling (trackpad) wins; so does a view with nothing to scroll.
        if panGestureRecognizer.state == .began || panGestureRecognizer.state == .changed { return false }
        let v = p.velocity(in: self), m = maxOffset
        return horizontal ? (m.x > 0 && abs(v.x) > abs(v.y)) : (m.y > 0 && abs(v.y) > abs(v.x))
    }
    #endif
}

#if targetEnvironment(macCatalyst)
/// Delegate of a ScrollHost's mouse drag. A separate object, so the scroll view's own delegate methods stay as UIKit set them.
private final class DragGate: NSObject, UIGestureRecognizerDelegate {
    weak var host: ScrollHost?
    func gestureRecognizer(_ g: UIGestureRecognizer, shouldReceive touch: UITouch) -> Bool { host?.dragMayReceive(touch) ?? false }
    func gestureRecognizerShouldBegin(_ g: UIGestureRecognizer) -> Bool { host?.dragMayBegin(g) ?? false }
}
#endif

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

/// A multiline TextInput: a UITextView inside a plain box, so the painted background and border stay put while
/// the text scrolls. It grows with its text unless the style fixes its height.
final class PxTextArea: UIView, UITextViewDelegate {
    let field = UITextView()
    private let hint = UILabel()
    var insets = UIEdgeInsets.zero { didSet { setNeedsLayout() } }
    var maxLength = 0
    var selectOnFocus = false
    var onChange: ((String) -> Void)?
    var onFocus: (() -> Void)?
    var onBlur: (() -> Void)?

    var text: String {
        get { field.text ?? "" }
        set { field.text = newValue; hint.isHidden = !newValue.isEmpty }
    }
    var placeholder: String? { get { hint.text } set { hint.text = newValue; setNeedsLayout() } }
    var placeholderColor: UIColor { get { hint.textColor } set { hint.textColor = newValue } }
    var font: UIFont? {
        get { field.font }
        set { field.font = newValue; hint.font = newValue; setNeedsLayout() }
    }

    override init(frame: CGRect) {
        super.init(frame: frame)
        field.backgroundColor = .clear
        field.textContainerInset = .zero
        field.textContainer.lineFragmentPadding = 0
        field.delegate = self
        hint.numberOfLines = 0
        hint.textColor = .placeholderText
        hint.isUserInteractionEnabled = false
        addSubview(field)
        addSubview(hint)
    }

    required init?(coder: NSCoder) { fatalError("not used") }

    override func layoutSubviews() {
        super.layoutSubviews()
        let r = bounds.inset(by: insets)
        field.frame = r
        let h = hint.sizeThatFits(CGSize(width: r.width, height: .greatestFiniteMagnitude)).height
        hint.frame = CGRect(x: r.minX, y: r.minY, width: r.width, height: min(h, r.height))
    }

    /// Height of the text (at least one line) when it is `width` pt wide.
    func contentHeight(_ width: CGFloat) -> CGFloat {
        let line = field.font?.lineHeight ?? 17
        return max(line, field.sizeThatFits(CGSize(width: width, height: .greatestFiniteMagnitude)).height)
    }

    func textViewDidChange(_ tv: UITextView) {
        if maxLength > 0, let s = tv.text, s.count > maxLength { tv.text = String(s.prefix(maxLength)) }
        hint.isHidden = !(tv.text ?? "").isEmpty
        onChange?(tv.text ?? "")
    }

    func textViewDidBeginEditing(_ tv: UITextView) {
        if selectOnFocus { DispatchQueue.main.async { tv.selectAll(nil) } }
        onFocus?()
    }

    func textViewDidEndEditing(_ tv: UITextView) { onBlur?() }
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

/// Vector shape: replays move/line/cubic/close commands scaled from a `viewbox` square to the view size.
final class PxPath: UIView {
    private let shape = CAShapeLayer()
    private var cmds: [[Double]] = []
    private var box: CGFloat = 24
    var strokeWidth: CGFloat = 2 { didSet { rebuild() } }
    var strokeColorCache: UIColor?
    var fillColorCache: UIColor?

    override init(frame: CGRect) {
        super.init(frame: frame)
        isUserInteractionEnabled = false
        shape.lineCap = .round; shape.lineJoin = .round
        shape.fillColor = nil; shape.strokeColor = nil
        layer.addSublayer(shape)
    }
    required init?(coder: NSCoder) { fatalError() }

    func setCommands(_ c: [[Double]]) { cmds = c; rebuild() }
    func setBox(_ b: CGFloat) { box = b; rebuild() }
    func setColors(stroke: UIColor?, fill: UIColor?) { shape.strokeColor = stroke?.cgColor; shape.fillColor = fill?.cgColor }

    override func layoutSubviews() { super.layoutSubviews(); rebuild() }

    private func rebuild() {
        let s = min(bounds.width, bounds.height) / box
        shape.frame = bounds
        shape.lineWidth = strokeWidth * s
        let ox = (bounds.width - box * s) / 2, oy = (bounds.height - box * s) / 2
        let p = UIBezierPath()
        func pt(_ x: Double, _ y: Double) -> CGPoint { CGPoint(x: ox + CGFloat(x) * s, y: oy + CGFloat(y) * s) }
        for c in cmds {
            switch Int(c[0]) {
            case 0: p.move(to: pt(c[1], c[2]))
            case 1: p.addLine(to: pt(c[1], c[2]))
            case 2: p.addCurve(to: pt(c[5], c[6]), controlPoint1: pt(c[1], c[2]), controlPoint2: pt(c[3], c[4]))
            default: p.close()
            }
        }
        shape.path = p.cgPath
    }
}

/// Native stack host. Screens are its subviews (last = top). Pushes slide in from the right over a parallax-shifted
/// previous screen, pops slide out, and a left-edge drag pops interactively. Motion uses UIKit animations, so Python
/// is not in the loop while a transition plays. Screens are moved with translation-only transforms; the layout
/// engine keeps owning their frames.
final class PxNav: PxGroup, UIGestureRecognizerDelegate {
    var animated = true
    var gestureEnabled = true
    var onPop: (() -> Void)?
    /// Screens kept only until their pop animation ends.
    private(set) var lingering = Set<UIView>()

    private lazy var edge: UIScreenEdgePanGestureRecognizer = {
        let g = UIScreenEdgePanGestureRecognizer(target: self, action: #selector(panned(_:)))
        g.edges = .left; g.delegate = self
        return g
    }()

    override init(frame: CGRect) {
        super.init(frame: frame)
        addGestureRecognizer(edge)
    }
    required init?(coder: NSCoder) { fatalError() }

    private func live() -> [UIView] { subviews.filter { !lingering.contains($0) } }
    private func parallax(_ w: CGFloat) -> CGFloat { w * 0.25 }
    private func slide(_ v: UIView?, to x: CGFloat, _ duration: TimeInterval, done: (() -> Void)? = nil) {
        UIView.animate(withDuration: duration, delay: 0, options: [.curveEaseOut, .allowUserInteraction], animations: {
            v?.transform = CGAffineTransform(translationX: x, y: 0)
        }, completion: { _ in done?() })
    }

    override func gestureRecognizerShouldBegin(_ g: UIGestureRecognizer) -> Bool {
        g === edge ? gestureEnabled && live().count > 1 : super.gestureRecognizerShouldBegin(g)
    }

    func pushed(_ v: UIView) {
        let l = live()
        guard animated, bounds.width > 0, let i = l.firstIndex(of: v), i > 0 else { return }
        let w = bounds.width
        v.transform = CGAffineTransform(translationX: w, y: 0)
        slide(v, to: 0, 0.32)
        slide(l[i - 1], to: -parallax(w), 0.32)
    }

    /// Returns true when the view stays until its exit animation ends.
    func popped(_ v: UIView) -> Bool {
        let w = bounds.width
        guard animated, w > 0, v.superview === self, v.transform.tx < w * 0.99 else { return false }
        lingering.insert(v)
        slide(v, to: w, 0.26) { [weak self, weak v] in
            guard let self = self, let v = v else { return }
            self.lingering.remove(v); v.removeFromSuperview()
        }
        slide(live().last, to: 0, 0.26)
        return true
    }

    @objc private func panned(_ g: UIScreenEdgePanGestureRecognizer) {
        let l = live()
        guard let top = l.last else { return }
        let below = l.count > 1 ? l[l.count - 2] : nil
        let w = bounds.width
        let dx = max(0, min(w, g.translation(in: self).x))
        switch g.state {
        case .changed:
            top.transform = CGAffineTransform(translationX: dx, y: 0)
            below?.transform = CGAffineTransform(translationX: -parallax(w) * (1 - dx / w), y: 0)
        case .ended, .cancelled, .failed:
            let commit = g.state == .ended && (dx > w * 0.35 || (g.velocity(in: self).x > 900 && dx > 24))
            if commit {
                slide(top, to: w, 0.18) { [weak self] in self?.onPop?() }
                slide(below, to: 0, 0.18)
            } else {
                slide(top, to: 0, 0.2)
                slide(below, to: -parallax(w), 0.2)
            }
        default: break
        }
    }
}
