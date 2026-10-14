import UIKit

/// Applies JSON op batches on the main thread. Keeps id -> UIView. Root id is 1.
final class OpApplier {
    private var views: [Int: UIView] = [:]
    private let sendEvent: (String) -> Void

    init(container: UIView, sendEvent: @escaping (String) -> Void) {
        self.sendEvent = sendEvent
        // Root id 1 is implicit in the ops protocol: it is never created by the reconciler.
        let root = PyxpoView()
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
    }

    func apply(_ batch: String) {
        guard let data = batch.data(using: .utf8),
              let ops = (try? JSONSerialization.jsonObject(with: data)) as? [[String: Any]] else { return }
        for o in ops {
            guard let op = o["op"] as? String else { continue }
            switch op {
            case "create":
                create(o["id"] as? Int ?? 0, o["type"] as? String ?? "View", o["props"] as? [String: Any] ?? [:])
            case "update":
                update(o["id"] as? Int ?? 0, o["props"] as? [String: Any] ?? [:], o["removed"] as? [String] ?? [])
            case "insert":
                insert(o["parent"] as? Int ?? 0, o["id"] as? Int ?? 0, o["index"] as? Int ?? 0)
            case "remove":
                if let v = views[o["id"] as? Int ?? 0] { v.removeFromSuperview(); relayout(v) }
            case "delete":
                views.removeValue(forKey: o["id"] as? Int ?? 0)
            default: break
            }
        }
        views[1]?.setNeedsLayout()
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
            let l = UILabel(); l.numberOfLines = 0; v = l
        case "Button":
            let b = UIButton(type: .system)
            b.addAction(UIAction { [weak self] _ in self?.event("press", id) }, for: .touchUpInside)
            v = b
        case "TextInput":
            let t = UITextField(); t.borderStyle = .roundedRect
            t.addAction(UIAction { [weak self, weak t] _ in
                self?.event("change_text", id, ["value": t?.text ?? ""])
            }, for: .editingChanged)
            v = t
        case "Image": v = UIImageView()
        case "ScrollView": v = ScrollHost()
        default: v = PyxpoView()
        }
        views[id] = v
        update(id, props, [])
    }

    private func update(_ id: Int, _ props: [String: Any], _ removed: [String]) {
        guard let v = views[id] else { return }
        if removed.contains("style") { applyStyle(v, [:]) }
        for (k, val) in props {
            switch k {
            case "text":
                let s = val as? String ?? ""
                if let b = v as? UIButton { b.setTitle(s, for: .normal) }
                else if let l = v as? UILabel { l.text = s }
            case "value":
                if let t = v as? UITextField {
                    let s = val as? String ?? ""
                    if t.text != s { t.text = s }
                }
            case "placeholder": (v as? UITextField)?.placeholder = val as? String
            case "style": applyStyle(v, val as? [String: Any] ?? [:])
            default: break
            }
        }
        relayout(v)
    }

    private func num(_ s: [String: Any], _ k: String, _ d: CGFloat) -> CGFloat {
        (s[k] as? NSNumber).map { CGFloat(truncating: $0) } ?? d
    }

    private func applyStyle(_ v: UIView, _ s: [String: Any]) {
        let layout = (v as? ScrollHost)?.content ?? (v as? PyxpoView)
        if let l = layout {
            l.row = (s["flex_direction"] as? String) == "row"
            l.gap = num(s, "gap", 0)
            l.alignItems = s["align_items"] as? String ?? "stretch"
            l.justify = s["justify_content"] as? String ?? "start"
            l.padding = num(s, "padding", 0)
        }
        v.px.width = num(s, "width", -1)
        v.px.height = num(s, "height", -1)
        v.px.flex = num(s, "flex", 0)
        v.px.margin = num(s, "margin", 0)
        if let c = s["background_color"] as? String { v.backgroundColor = Self.color(c) } else { v.backgroundColor = .clear }
        let size = num(s, "font_size", 14)
        let weight: UIFont.Weight = (s["font_weight"] as? String) == "bold" ? .bold : .regular
        let font = UIFont.systemFont(ofSize: size, weight: weight)
        let col = (s["color"] as? String).flatMap(Self.color)
        if let l = v as? UILabel { l.font = font; l.textColor = col ?? .label }
        if let b = v as? UIButton { b.titleLabel?.font = font; if let c = col { b.setTitleColor(c, for: .normal) } }
        if let t = v as? UITextField { t.font = font; if let c = col { t.textColor = c } }
    }

    private static let named: [String: UIColor] = [
        "white": .white, "black": .black, "red": .red, "green": .green, "blue": .blue,
        "gray": .gray, "grey": .gray, "yellow": .yellow, "transparent": .clear,
    ]

    /// #RRGGBB, #AARRGGBB (Android order), or a basic color name.
    static func color(_ c: String) -> UIColor? {
        if let n = named[c.lowercased()] { return n }
        guard c.hasPrefix("#") else { return nil }
        var x: UInt64 = 0
        let hex = String(c.dropFirst())
        guard Scanner(string: hex).scanHexInt64(&x) else { return nil }
        switch hex.count {
        case 6: return UIColor(red: CGFloat((x >> 16) & 255) / 255, green: CGFloat((x >> 8) & 255) / 255,
                               blue: CGFloat(x & 255) / 255, alpha: 1)
        case 8: return UIColor(red: CGFloat((x >> 16) & 255) / 255, green: CGFloat((x >> 8) & 255) / 255,
                               blue: CGFloat(x & 255) / 255, alpha: CGFloat((x >> 24) & 255) / 255)
        default: return nil
        }
    }

    private func container(_ id: Int) -> UIView? {
        guard let p = views[id] else { return nil }
        return (p as? ScrollHost)?.content ?? (p is PyxpoView ? p : nil)
    }

    private func insert(_ parent: Int, _ id: Int, _ index: Int) {
        guard let g = container(parent), let v = views[id] else { return }
        v.removeFromSuperview()
        g.insertSubview(v, at: min(index, g.subviews.count))
        relayout(g)
    }

    /// Re-measure from the nearest layout ancestor up (content size can change the whole tree).
    private func relayout(_ v: UIView) {
        var cur: UIView? = v
        while let c = cur { c.setNeedsLayout(); cur = c.superview }
    }
}
