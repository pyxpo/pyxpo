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
    private var boxes: [Int: BoxLayer] = [:]
    private var texts: [Int: String] = [:]
    private var spans: [Int: [[String: Any]]] = [:]
    private static var fontCache: [String: String] = [:]
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
        var a11yDirty = removed.contains { $0.hasPrefix("accessib") }
        if removed.contains("style") { applyStyle(id, v, [:]) }
        if removed.contains("spans") {
            spans.removeValue(forKey: id)
            if let l = v as? UILabel { renderLabel(id, l, styles[id] ?? [:]) }
            px_node_mark_dirty(tree, Int32(id))
        }
        for (k, val) in props {
            switch k {
            case "text":
                let s = val as? String ?? ""
                texts[id] = s
                if let b = v as? UIButton { b.setTitle(s, for: .normal) }
                else if let l = v as? UILabel { renderLabel(id, l, styles[id] ?? [:]) }
                px_node_mark_dirty(tree, Int32(id))
            case "spans":
                spans[id] = val as? [[String: Any]]
                if let l = v as? UILabel { renderLabel(id, l, styles[id] ?? [:]) }
                px_node_mark_dirty(tree, Int32(id))
            case "value":
                if let t = v as? UITextField {
                    let s = val as? String ?? ""
                    if t.text != s { t.text = s; px_node_mark_dirty(tree, Int32(id)) }
                }
            case "placeholder": (v as? UITextField)?.placeholder = val as? String
            case "style": applyStyle(id, v, val as? [String: Any] ?? [:])
            case "on_press", "on_press_in", "on_press_out", "on_long_press":
                if let g = v as? PxGroup, g.onTouch == nil {
                    g.isUserInteractionEnabled = true
                    g.onTouch = { [weak self] name, p in
                        var pl: [String: Any] = [:]
                        if let p = p { pl = ["x": p.x, "y": p.y] }
                        self?.event(name, id, pl)
                    }
                }
            case let k where k.hasPrefix("accessib"): a11yDirty = true
            default: break
            }
        }
        if a11yDirty {
            var a = a11y[id] ?? [:]
            for k in removed where k.hasPrefix("accessib") { a.removeValue(forKey: k) }
            for (k, val) in props where k.hasPrefix("accessib") { a[k] = val }
            a11y[id] = a
            applyA11y(v, a)
        }
        if !batching { flush() }
    }

    private var a11y: [Int: [String: Any]] = [:]

    private func applyA11y(_ v: UIView, _ a: [String: Any]) {
        let st = a["accessibility_state"] as? [String: Any] ?? [:]
        let role = a["accessibility_role"] as? String ?? ""
        if let acc = a["accessible"] as? Bool { v.isAccessibilityElement = acc }
        else if a["accessibility_label"] != nil || !role.isEmpty { v.isAccessibilityElement = true }
        v.accessibilityLabel = a["accessibility_label"] as? String
        v.accessibilityHint = a["accessibility_hint"] as? String
        var parts: [String] = []
        if let c = st["checked"] as? Bool { parts.append(c ? "checked" : "not checked") }
        if (st["selected"] as? Bool) == true { parts.append("selected") }
        if let val = a["accessibility_value"] as? String { parts.append(val) }
        v.accessibilityValue = parts.isEmpty ? nil : parts.joined(separator: ", ")
        var tr: UIAccessibilityTraits = []
        switch role {
        case "button", "imagebutton": tr.insert(.button)
        case "link": tr.insert(.link)
        case "header": tr.insert(.header)
        case "image": tr.insert(.image)
        case "switch", "checkbox", "radio": tr.insert(.button)
        default: break
        }
        if (st["selected"] as? Bool) == true || (st["checked"] as? Bool) == true { tr.insert(.selected) }
        if (st["disabled"] as? Bool) == true { tr.insert(.notEnabled) }
        v.accessibilityTraits = tr
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
        boxes.removeValue(forKey: id)
        texts.removeValue(forKey: id)
        spans.removeValue(forKey: id)
        a11y.removeValue(forKey: id)
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
        paintBox(id, v, s)
        v.alpha = min(max(num(s, "opacity", 1), 0), 1)
        let sc = num(s, "scale", 1)
        v.transform = CGAffineTransform(translationX: num(s, "translate_x"), y: num(s, "translate_y"))
            .rotated(by: num(s, "rotate") * .pi / 180)
            .scaledBy(x: sc * num(s, "scale_x", 1), y: sc * num(s, "scale_y", 1))
        paintText(id, v, s)
    }

    private func paintBox(_ id: Int, _ v: UIView, _ s: [String: Any]) {
        var spec = BoxSpec()
        spec.bg = col(s, "background_color")
        spec.radii = ["top_left", "top_right", "bottom_right", "bottom_left"].map { num(s, "border_" + $0 + "_radius") }
        let sides = ["left", "top", "right", "bottom"]
        spec.bw = sides.map { num(s, "border_" + $0 + "_width") }
        spec.bc = sides.map { col(s, "border_" + $0 + "_color") ?? .black }
        spec.clip = (s["overflow"] as? String) == "hidden"
        if let g = s["linear_gradient"] as? [String: Any], let cs = g["colors"] as? [NSNumber],
           let st = g["stops"] as? [NSNumber] {
            spec.gradColors = cs.map { Self.color($0.uint32Value) }
            spec.gradStops = st.map { CGFloat(truncating: $0) }
            spec.gradAngle = CGFloat(truncating: (g["angle"] as? NSNumber) ?? 180)
        }
        let op = num(s, "shadow_opacity", s["shadow_radius"] != nil || s["shadow_color"] != nil ? 1 : 0)
        let elev = num(s, "elevation")
        let L = v.layer
        L.shadowColor = (col(s, "shadow_color") ?? .black).cgColor
        L.shadowOpacity = Float(min(max(op > 0 || elev > 0 ? max(op, elev > 0 ? 0.25 : 0) : 0, 0), 1))
        L.shadowRadius = max(num(s, "shadow_radius"), elev)
        L.shadowOffset = CGSize(width: num(s, "shadow_offset_x"), height: num(s, "shadow_offset_y") + (elev > 0 && s["shadow_offset_y"] == nil ? elev / 2 : 0))
        if spec.hasBox || L.shadowOpacity > 0 || spec.clip {
            let b = boxes[id] ?? { let n = BoxLayer(); if let l = v as? PxLabel { l.box = n } else { v.layer.insertSublayer(n, at: 0) }; boxes[id] = n; return n }()
            b.spec = spec
            layoutBox(id, v)
        } else if let b = boxes.removeValue(forKey: id) {
            b.removeFromSuperlayer()
            (v as? PxLabel)?.box = nil
            v.setNeedsDisplay()
            v.layer.shadowPath = nil
            v.layer.mask = nil
        }
        v.clipsToBounds = spec.clip && !spec.radii.contains { $0 > 0 }
    }

    /// Re-draw the box under the view after its size or style changed.
    private func layoutBox(_ id: Int, _ v: UIView) {
        guard let b = boxes[id] else { return }
        let r = CGRect(origin: .zero, size: v.bounds.size)
        b.update(r)
        v.setNeedsDisplay()
        if v.layer.shadowOpacity > 0 { v.layer.shadowPath = b.outerPath(r).cgPath } else { v.layer.shadowPath = nil }
        if b.spec.clip && b.spec.radii.contains(where: { $0 > 0 }) {
            let m = CAShapeLayer(); m.path = b.outerPath(r).cgPath
            v.layer.mask = m
        } else { v.layer.mask = nil }
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

    /// Font from a normalized text style: custom file, generic family, system weight, italic, Dynamic Type.
    private static func uiFont(_ s: [String: Any], _ size: CGFloat? = nil) -> UIFont {
        let base = size ?? CGFloat(truncating: (s["font_size"] as? NSNumber) ?? 14)
        let scaled = (s["allow_font_scaling"] as? Bool) ?? true
        let pt = scaled ? base * fontScale : base
        let italic = (s["font_style"] as? String) == "italic"
        var font: UIFont
        if let file = s["font_file"] as? String, let name = customFontName(file) {
            font = UIFont(name: name, size: pt) ?? .systemFont(ofSize: pt)
        } else {
            let w = weight(s["font_weight"])
            switch s["font_family"] as? String {
            case "monospace": font = .monospacedSystemFont(ofSize: pt, weight: w)
            case "serif":
                let d = UIFont.systemFont(ofSize: pt, weight: w).fontDescriptor.withDesign(.serif)
                font = d.map { UIFont(descriptor: $0, size: pt) } ?? .systemFont(ofSize: pt, weight: w)
            default: font = .systemFont(ofSize: pt, weight: w)
            }
        }
        if italic, let d = font.fontDescriptor.withSymbolicTraits(.traitItalic) { font = UIFont(descriptor: d, size: pt) }
        return font
    }

    private static func customFontName(_ path: String) -> String? {
        if let n = fontCache[path] { return n.isEmpty ? nil : n }
        var name = ""
        if let prov = CGDataProvider(filename: path), let cg = CGFont(prov) {
            CTFontManagerRegisterGraphicsFont(cg, nil)  // already registered returns false: still usable
            name = (cg.postScriptName as String?) ?? ""
        }
        fontCache[path] = name
        return name.isEmpty ? nil : name
    }

    private func attrs(_ s: [String: Any], _ para: NSParagraphStyle?, isSpan: Bool = false) -> [NSAttributedString.Key: Any] {
        var a: [NSAttributedString.Key: Any] = [.font: Self.uiFont(s)]
        a[.foregroundColor] = col(s, "color") ?? UIColor.label
        if isSpan, let bg = col(s, "background_color") { a[.backgroundColor] = bg }
        if let ls = s["letter_spacing"] as? NSNumber { a[.kern] = CGFloat(truncating: ls) }
        let deco = s["text_decoration"] as? String ?? ""
        if deco.contains("underline") { a[.underlineStyle] = NSUnderlineStyle.single.rawValue }
        if deco.contains("line-through") { a[.strikethroughStyle] = NSUnderlineStyle.single.rawValue }
        if let p = para { a[.paragraphStyle] = p }
        if s["text_shadow_color"] != nil || s["text_shadow_radius"] != nil {
            let sh = NSShadow()
            sh.shadowColor = col(s, "text_shadow_color") ?? .black
            sh.shadowBlurRadius = num(s, "text_shadow_radius")
            sh.shadowOffset = CGSize(width: num(s, "text_shadow_offset_x"), height: num(s, "text_shadow_offset_y"))
            a[.shadow] = sh
        }
        return a
    }

    /// Label text as an attributed string: style attributes plus optional nested-Text spans.
    private func renderLabel(_ id: Int, _ l: UILabel, _ s: [String: Any]) {
        let para = NSMutableParagraphStyle()
        switch s["text_align"] as? String {
        case "center": para.alignment = .center
        case "right": para.alignment = .right
        default: para.alignment = .natural
        }
        let n = Int(num(s, "number_of_lines"))
        para.lineBreakMode = n > 0 ? .byTruncatingTail : .byWordWrapping
        if let lh = s["line_height"] as? NSNumber {
            let h = CGFloat(truncating: lh) * ((s["allow_font_scaling"] as? Bool) ?? true ? Self.fontScale : 1)
            // extra space below each line: same result as Android's lineHeight, and avoids UILabel
            // drawing nothing with min/max line height
            para.lineSpacing = max(0, h - Self.uiFont(s).lineHeight)
        }
        let out = NSMutableAttributedString()
        if let sp = spans[id], !sp.isEmpty {
            for o in sp {
                var st = s
                for (k, v) in (o["style"] as? [String: Any] ?? [:]) { st[k] = v }
                out.append(NSAttributedString(string: o["text"] as? String ?? "", attributes: attrs(st, para, isSpan: true)))
            }
        } else {
            out.append(NSAttributedString(string: texts[id] ?? "", attributes: attrs(s, para)))
        }
        l.attributedText = out
        l.numberOfLines = n > 0 ? n : 0
        l.lineBreakMode = para.lineBreakMode
    }

    private func paintText(_ id: Int, _ v: UIView, _ s: [String: Any]) {
        guard v is UILabel || v is UIButton || v is UITextField else { return }
        let font = Self.uiFont(s)
        let c = col(s, "color")
        let align: NSTextAlignment
        switch s["text_align"] as? String {
        case "center": align = .center
        case "right": align = .right
        default: align = .natural
        }
        if let l = v as? UILabel {
            renderLabel(id, l, s)
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
        for (id, s) in styles { if let v = views[id] { paintText(id, v, s) } }
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
                if let v = views[id] {
                    // bounds + center, not frame: frame is undefined under a transform
                    v.bounds = CGRect(origin: v.bounds.origin, size: r.size)
                    v.center = CGPoint(x: r.midX, y: r.midY)
                    layoutBox(id, v)
                }
            }
        }
    }
}
