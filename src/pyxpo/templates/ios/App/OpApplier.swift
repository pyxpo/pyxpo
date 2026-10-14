import UIKit

/// Applies JSON op batches (wire v2) on the main thread. Styles arrive normalized (pt, ARGB ints).
/// Layout is done by the shared C engine; this class only places frames, measures leaves and paints boxes.
final class OpApplier {
    private static let content = 0x40000000  // id bit for a ScrollView's synthetic content node
    private static let leaves: Set<String> = ["Text", "Button", "TextInput", "Image"]

    private var views: [Int: UIView] = [:]
    private var types: [Int: String] = [:]
    private var styles: [Int: [String: Any]] = [:]
    private var pads: [Int: UIEdgeInsets] = [:]
    private var propIds: [String: Int32] = [:]
    private var tree: OpaquePointer!
    private let root = PxRoot()
    private var rootSize = CGSize.zero
    private var sentEnv: String?
    private var batching = false
    private let sendEvent: (String) -> Void
    private var scale: CGFloat { UIScreen.main.scale }

    /// Dynamic Type scale relative to the default body size.
    static var fontScale: CGFloat { UIFontMetrics.default.scaledValue(for: 100) / 100 }

    /// Env snapshot for the Python side (before the first op). Sizes in pt.
    static func envJson(window: CGSize, screen: CGSize, dark: Bool) -> [String: Any] {
        [
            "os": "ios",
            "window": ["width": Double(window.width), "height": Double(window.height)],
            "screen": ["width": Double(screen.width), "height": Double(screen.height)],
            "scale": Double(UIScreen.main.scale),
            "font_scale": Double(fontScale),
            "color_scheme": dark ? "dark" : "light",
        ]
    }

    init(container: UIView, sendEvent: @escaping (String) -> Void) {
        self.sendEvent = sendEvent
        let fn: PxMeasureFn = { ctx, id, w, wm, h, hm, ow, oh in
            let a = Unmanaged<OpApplier>.fromOpaque(ctx!).takeUnretainedValue()
            let s = a.measure(Int(id), w, Int(wm), h, Int(hm))
            ow?.pointee = Float(s.width)
            oh?.pointee = Float(s.height)
        }
        tree = px_tree_new(fn, Unmanaged.passUnretained(self).toOpaque())
        // Root id 1 is implicit in the ops protocol: it is never created by the reconciler.
        root.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(root)
        let g = container.safeAreaLayoutGuide
        NSLayoutConstraint.activate([
            root.leadingAnchor.constraint(equalTo: g.leadingAnchor),
            root.trailingAnchor.constraint(equalTo: g.trailingAnchor),
            root.topAnchor.constraint(equalTo: g.topAnchor),
            root.bottomAnchor.constraint(equalTo: g.bottomAnchor),
        ])
        views[1] = root
        types[1] = "Root"
        root.onSize = { [weak self] s in self?.onRootSize(s) }
        root.onTraits = { [weak self] in self?.configChanged() }
        NotificationCenter.default.addObserver(forName: UIContentSizeCategory.didChangeNotification, object: nil,
                                               queue: .main) { [weak self] _ in self?.configChanged() }
    }

    deinit { px_tree_free(tree) }

    // -- ops -----------------------------------------------------------------------------------------
    func apply(_ batch: String) {
        guard let data = batch.data(using: .utf8),
              let ops = (try? JSONSerialization.jsonObject(with: data)) as? [[String: Any]] else { return }
        batching = true
        for o in ops {
            guard let op = o["op"] as? String else { continue }
            let id = o["id"] as? Int ?? 0
            switch op {
            case "create": create(id, o["type"] as? String ?? "View", o["props"] as? [String: Any] ?? [:])
            case "update": update(id, o["props"] as? [String: Any] ?? [:], o["removed"] as? [String] ?? [])
            case "insert": insert(o["parent"] as? Int ?? 0, id, o["index"] as? Int ?? 0)
            case "remove": remove(o["parent"] as? Int ?? 0, id)
            case "delete": delete(id)
            default: break
            }
        }
        batching = false
        flush()
    }

    private func event(_ name: String, _ id: Int, _ payload: [String: Any] = [:]) {
        let obj: [String: Any] = ["event": name, "id": id, "payload": payload]
        if let d = try? JSONSerialization.data(withJSONObject: obj), let s = String(data: d, encoding: .utf8) {
            sendEvent(s)
        }
    }

    private func create(_ id: Int, _ type: String, _ props: [String: Any]) {
        let v: UIView
        switch type {
        case "Text":
            let l = PxLabel(); l.numberOfLines = 0; v = l
        case "Button":
            let b = UIButton(type: .system)
            b.addAction(UIAction { [weak self] _ in self?.event("press", id) }, for: .touchUpInside)
            v = b
        case "TextInput":
            let t = PxTextField()
            t.addAction(UIAction { [weak self, weak t] _ in
                self?.event("change_text", id, ["value": t?.text ?? ""])
            }, for: .editingChanged)
            v = t
        case "Image": v = UIImageView()
        case "ScrollView": v = ScrollHost()
        default: v = PxGroup()
        }
        views[id] = v
        types[id] = type
        px_node_create(tree, Int32(id))
        if Self.leaves.contains(type) { px_node_set_measured(tree, Int32(id), 1) }
        if type == "ScrollView" {
            let c = Int32(id | Self.content)
            px_node_create(tree, c)
            px_node_insert(tree, Int32(id), c, 0)
            px_node_set_num(tree, c, prop("flex_shrink"), 0)
        }
        update(id, props, [])
    }

    private func update(_ id: Int, _ props: [String: Any], _ removed: [String]) {
        guard let v = views[id] else { return }
        if removed.contains("style") { applyStyle(id, v, [:]) }
        for (k, val) in props {
            switch k {
            case "text":
                let s = val as? String ?? ""
                if let b = v as? UIButton { b.setTitle(s, for: .normal) }
                else if let l = v as? UILabel { l.text = s }
                px_node_mark_dirty(tree, Int32(id))
            case "value":
                if let t = v as? UITextField {
                    let s = val as? String ?? ""
                    if t.text != s { t.text = s; px_node_mark_dirty(tree, Int32(id)) }
                }
            case "placeholder": (v as? UITextField)?.placeholder = val as? String
            case "style": applyStyle(id, v, val as? [String: Any] ?? [:])
            default: break
            }
        }
        if !batching { flush() }
    }

    private func parentNode(_ parent: Int) -> Int32 {
        Int32(types[parent] == "ScrollView" ? parent | Self.content : parent)
    }

    private func groupOf(_ parent: Int) -> UIView? {
        guard let p = views[parent] else { return nil }
        if let s = p as? ScrollHost { return s.content }
        return p is PxGroup || p is PxRoot ? p : nil
    }

    private func insert(_ parent: Int, _ id: Int, _ index: Int) {
        guard let g = groupOf(parent), let v = views[id] else { return }
        v.removeFromSuperview()
        g.insertSubview(v, at: min(index, g.subviews.count))
        px_node_remove(tree, parentNode(parent), Int32(id))
        px_node_insert(tree, parentNode(parent), Int32(id), Int32(index))
    }

    private func remove(_ parent: Int, _ id: Int) {
        views[id]?.removeFromSuperview()
        px_node_remove(tree, parentNode(parent), Int32(id))
    }

    private func delete(_ id: Int) {
        views.removeValue(forKey: id)?.removeFromSuperview()
        if types.removeValue(forKey: id) == "ScrollView" { px_node_delete(tree, Int32(id | Self.content)) }
        px_node_delete(tree, Int32(id))
        styles.removeValue(forKey: id)
        pads.removeValue(forKey: id)
    }

    // -- style ---------------------------------------------------------------------------------------
    private func prop(_ name: String) -> Int32 {
        if let p = propIds[name] { return p }
        let p = px_prop_id(name)
        propIds[name] = p
        return p
    }

    private func applyStyle(_ id: Int, _ v: UIView, _ s: [String: Any]) {
        let old = styles[id] ?? [:]
        let nid = Int32(id)
        for (k, nv) in s where "\(old[k] ?? "")" != "\(nv)" || old[k] == nil {
            let p = prop(k)
            if p < 0 { continue }
            if let n = nv as? NSNumber { px_node_set_num(tree, nid, p, n.floatValue) }
            else if let str = nv as? String { px_node_set_str(tree, nid, p, str) }
        }
        for k in old.keys where s[k] == nil {
            let p = prop(k)
            if p >= 0 { px_node_reset(tree, nid, p) }
        }
        styles[id] = s
        paint(id, v, s)
        px_node_mark_dirty(tree, nid)
    }

    private func num(_ s: [String: Any], _ k: String, _ d: CGFloat = 0) -> CGFloat {
        (s[k] as? NSNumber).map { CGFloat(truncating: $0) } ?? d
    }

    static func color(_ argb: UInt32) -> UIColor {
        UIColor(red: CGFloat((argb >> 16) & 255) / 255, green: CGFloat((argb >> 8) & 255) / 255,
                blue: CGFloat(argb & 255) / 255, alpha: CGFloat((argb >> 24) & 255) / 255)
    }

    private func col(_ s: [String: Any], _ k: String) -> UIColor? {
        (s[k] as? NSNumber).map { Self.color($0.uint32Value) }
    }

    private func paint(_ id: Int, _ v: UIView, _ s: [String: Any]) {
        // leaf views draw their own content, so padding + border become content insets
        if Self.leaves.contains(types[id] ?? "") {
            func e(_ side: String) -> CGFloat { num(s, "padding_" + side) + num(s, "border_" + side + "_width") }
            let p = UIEdgeInsets(top: e("top"), left: e("left"), bottom: e("bottom"), right: e("right"))
            pads[id] = p
            (v as? PxLabel)?.insets = p
            (v as? PxTextField)?.insets = p
            (v as? UIButton)?.contentEdgeInsets = p
        }
        v.backgroundColor = col(s, "background_color") ?? .clear
        let r = num(s, "border_top_left_radius")
        v.layer.cornerRadius = r
        let bw = num(s, "border_top_width")
        v.layer.borderWidth = bw
        v.layer.borderColor = (col(s, "border_top_color") ?? .black).cgColor
        let clip = (s["overflow"] as? String) == "hidden"
        v.clipsToBounds = clip
        v.alpha = min(max(num(s, "opacity", 1), 0), 1)
        paintText(v, s)
    }

    private static func weight(_ w: Any?) -> UIFont.Weight {
        let n: Int
        switch w {
        case let s as String: n = s == "bold" ? 700 : (Int(s) ?? 400)
        case let x as NSNumber: n = x.intValue
        default: n = 400
        }
        switch n {
        case ..<150: return .ultraLight
        case ..<250: return .thin
        case ..<350: return .light
        case ..<450: return .regular
        case ..<550: return .medium
        case ..<650: return .semibold
        case ..<750: return .bold
        case ..<850: return .heavy
        default: return .black
        }
    }

    private func paintText(_ v: UIView, _ s: [String: Any]) {
        guard v is UILabel || v is UIButton || v is UITextField else { return }
        let size = num(s, "font_size", 14) * Self.fontScale
        var font = UIFont.systemFont(ofSize: size, weight: Self.weight(s["font_weight"]))
        if (s["font_style"] as? String) == "italic",
           let d = font.fontDescriptor.withSymbolicTraits(.traitItalic) {
            font = UIFont(descriptor: d, size: size)
        }
        let c = col(s, "color")
        let align: NSTextAlignment
        switch s["text_align"] as? String {
        case "center": align = .center
        case "right": align = .right
        default: align = .natural
        }
        if let l = v as? UILabel {
            l.font = font
            l.textColor = c ?? .label
            l.textAlignment = align
            let n = Int(num(s, "number_of_lines"))
            l.numberOfLines = n > 0 ? n : 0
            l.lineBreakMode = n > 0 ? .byTruncatingTail : .byWordWrapping
        } else if let b = v as? UIButton {
            b.titleLabel?.font = font
            b.setTitleColor(c, for: .normal)
        } else if let t = v as? UITextField {
            t.font = font
            t.textColor = c ?? .label
            t.textAlignment = align
        }
    }

    // -- layout --------------------------------------------------------------------------------------
    /// Leaf measure callback from the engine. w/h are inner sizes in pt.
    fileprivate func measure(_ id: Int, _ w: Float, _ wm: Int, _ h: Float, _ hm: Int) -> CGSize {
        guard let v = views[id] else { return .zero }
        let inf = CGFloat.greatestFiniteMagnitude
        let lw = wm == 2 || w.isNaN || w > 1e6 ? inf : CGFloat(max(0, w))
        let lh = hm == 2 || h.isNaN || h > 1e6 ? inf : CGFloat(max(0, h))
        var s: CGSize = .zero
        if let l = v as? UILabel { s = l.sizeThatFits(CGSize(width: lw, height: lh)) }
        else if let b = v as? UIButton { s = b.titleLabel?.sizeThatFits(CGSize(width: lw, height: lh)) ?? .zero }
        else if let t = v as? UITextField { s = CGSize(width: 0, height: t.font?.lineHeight ?? 17) }
        else if let i = v as? UIImageView { s = i.image?.size ?? .zero }
        if wm == 0 { s.width = lw }
        if hm == 0 { s.height = lh }
        let sc = scale
        return CGSize(width: ceil(s.width * sc) / sc, height: ceil(s.height * sc) / sc)
    }

    private func onRootSize(_ s: CGSize) {
        if s.width <= 0 || s.height <= 0 || s == rootSize { return }
        rootSize = s
        sendEnv()
        flush()
    }

    /// Sends the current window/scale/color scheme to Python when it changed.
    func sendEnv() {
        if rootSize.width <= 0 { return }
        var j = Self.envJson(window: rootSize, screen: UIScreen.main.bounds.size,
                             dark: root.traitCollection.userInterfaceStyle == .dark)
        j.removeValue(forKey: "os")
        guard let d = try? JSONSerialization.data(withJSONObject: j, options: [.sortedKeys]),
              let str = String(data: d, encoding: .utf8), str != sentEnv else { return }
        sentEnv = str
        event("env", 0, j)
    }

    /// Dynamic Type, dark mode or other trait change: fonts and leaf sizes may differ.
    func configChanged() {
        sendEnv()
        for (id, s) in styles { if let v = views[id] { paintText(v, s) } }
        for (id, t) in types where Self.leaves.contains(t) { px_node_mark_dirty(tree, Int32(id)) }
        flush()
    }

    private func flush() {
        if rootSize.width <= 0 { return }
        px_tree_calc(tree, Float(rootSize.width), Float(rootSize.height))
        var f = [Float](repeating: 0, count: 4)
        let n = px_tree_changed_count(tree)
        for i in 0..<n {
            let id = Int(px_tree_changed_at(tree, i, &f))
            let r = CGRect(x: CGFloat(f[0]), y: CGFloat(f[1]), width: CGFloat(f[2]), height: CGFloat(f[3]))
            if id == 1 { continue }
            if id & Self.content != 0 {
                if let sh = views[id & ~Self.content] as? ScrollHost {
                    sh.content.frame = CGRect(origin: .zero, size: r.size)
                    sh.contentSize = r.size
                }
            } else {
                views[id]?.frame = r
            }
        }
    }
}
