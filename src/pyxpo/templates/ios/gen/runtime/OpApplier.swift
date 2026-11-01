import UIKit
import AudioToolbox

/// Applies JSON op batches (wire v2) on the main thread. Styles arrive normalized (pt, ARGB ints).
/// Layout is done by the shared C engine; this class only places frames, measures leaves and paints boxes.
final class OpApplier {
    private static let content = 0x40000000  // id bit for a ScrollView's synthetic content node
    private static let leaves: Set<String> = ["Text", "Button", "TextInput", "Image"]
    /// UIKit controls hosted for Switch / Slider / ActivityIndicator; they report an intrinsic size like leaves.
    private static let controls: Set<String> = ["NativeSwitch", "NativeSlider", "NativeSpinner"]
    /// The Mac app (Catalyst, Mac idiom): some UIKit control styling is unsupported and throws there.
    private static let macIdiom = UIDevice.current.userInterfaceIdiom == .mac

    private var views: [Int: UIView] = [:]
    private var types: [Int: String] = [:]
    private var styles: [Int: [String: Any]] = [:]
    private var pads: [Int: UIEdgeInsets] = [:]
    private var boxes: [Int: BoxLayer] = [:]
    private var texts: [Int: String] = [:]
    private var ctl: [Int: [String: Any]] = [:]   // merged props of native controls
    private var spans: [Int: [[String: Any]]] = [:]
    // Values a TextInput reported that Python has not echoed back yet. Python answers each change_text with a
    // render, so while the user types faster than that, renders carry values the field has already moved past.
    private var pendingText: [Int: [String]] = [:]
    private static var fontCache: [String: String] = [:]
    private var propIds: [String: Int32] = [:]
    private var tree: OpaquePointer!
    private let root = PxRoot()
    private var rootSize = CGSize.zero
    private var sentEnv: String?
    /// Native modules linked into this app (see `PxModuleRegistry`).
    private(set) lazy var modules = PxModuleHost(root: root) { [weak self] n, d in self?.event("module", 0, ["name": n, "data": d]) }
    private var kbHeight: CGFloat = 0
    private var rtl = false  // `I18nManager.set_rtl` from Python: frames mirrored, text aligned to the right
    private var batching = false
    private lazy var anim = Animated(emit: { [weak self] n, id, pl in self?.event(n, id, pl) },
                                     onFrame: { [weak self] t in self?.onAnimFrame(t) })
    private var binds: [Int: [String: Int]] = [:]   // view id -> style key -> animated node id
    private var depCache: [Int: Set<Int>] = [:]
    private let sendEvent: (String) -> Void
    private var scale: CGFloat { UIScreen.main.scale }

    /// Dynamic Type scale relative to the default body size.
    static var fontScale: CGFloat { UIFontMetrics.default.scaledValue(for: 100) / 100 }

    /// Env snapshot for the Python side (before the first op). Sizes in pt.
    static func envJson(window: CGSize, screen: CGSize, dark: Bool, insets: UIEdgeInsets = .zero,
                        keyboard: CGFloat = 0, startup: Bool = true) -> [String: Any] {
        var j: [String: Any] = [
            "insets": ["left": Double(insets.left), "top": Double(insets.top), "right": Double(insets.right),
                       "bottom": Double(insets.bottom)],
            "keyboard": ["visible": keyboard > 0, "height": Double(keyboard)],
            "os": "ios",
            "window": ["width": Double(window.width), "height": Double(window.height)],
            "screen": ["width": Double(screen.width), "height": Double(screen.height)],
            "scale": Double(UIScreen.main.scale),
            "font_scale": Double(fontScale),
            "color_scheme": dark ? "dark" : "light",
            "modules": PxModuleHost.names,
            "rtl": deviceRTL,
            "locale": Locale.current.identifier,
        ]
        if startup { j["module_constants"] = PxModuleHost.constants }
        return j
    }

    /// The device language is written right to left (Python decides whether the app follows it).
    static var deviceRTL: Bool {
        guard let l = Locale.preferredLanguages.first else { return false }
        return Locale.characterDirection(forLanguage: l) == .rightToLeft
    }

    let splash = PxSplash()

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
        PxAppConfig.apply(container: container)
        splash.show(in: container)
        // Edge to edge: the app draws under the status bar / home indicator. Insets go to Python (SafeArea).
        NSLayoutConstraint.activate([
            root.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            root.trailingAnchor.constraint(equalTo: container.trailingAnchor),
            root.topAnchor.constraint(equalTo: container.topAnchor),
            root.bottomAnchor.constraint(equalTo: container.bottomAnchor),
        ])
        views[1] = root
        types[1] = "Root"
        root.onSize = { [weak self] s in self?.onRootSize(s) }
        root.onTraits = { [weak self] in self?.configChanged() }
        NotificationCenter.default.addObserver(forName: UIContentSizeCategory.didChangeNotification, object: nil,
                                               queue: .main) { [weak self] _ in self?.configChanged() }
        let kbChange: (Notification) -> Void = { [weak self] n in
            guard let self = self else { return }
            if n.name == UIResponder.keyboardWillHideNotification { self.kbHeight = 0 }
            else if let f = n.userInfo?[UIResponder.keyboardFrameEndUserInfoKey] as? CGRect {
                self.kbHeight = max(0, UIScreen.main.bounds.height - f.minY)
            }
            self.sendEnv()
            self.flush()
        }
        for name in [UIResponder.keyboardWillChangeFrameNotification, UIResponder.keyboardWillHideNotification] {
            NotificationCenter.default.addObserver(forName: name, object: nil, queue: .main, using: kbChange)
        }
        let states: [(Notification.Name, String)] = [(UIApplication.didBecomeActiveNotification, "active"),
                                                     (UIApplication.willResignActiveNotification, "inactive"),
                                                     (UIApplication.didEnterBackgroundNotification, "background")]
        for (name, state) in states {
            NotificationCenter.default.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in
                self?.event("app_state", 0, ["state": state])
            }
        }
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
            case "anode": anim.anode(id, o["node"] as? [String: Any] ?? [:]); depCache.removeAll()
            case "anode_del": anim.anodeDel(id); depCache.removeAll()
            case "alisten": anim.alisten(id, o["on"] as? Bool ?? false)
            case "animate": anim.animate(id, o["anim"] as? [String: Any] ?? [:])
            case "astop": anim.astop(id)
            case "aset": anim.aset(o["vals"] as? [String: Any] ?? [:])
            case "call": call(id, o["module"] as? String ?? "", o["method"] as? String ?? "",
                              o["args"] as? [Any] ?? [], o["reply"] as? Bool ?? false)
            default: break
            }
        }
        batching = false
        flush()
        splash.batchApplied()
    }

    /// Dev builds: ask Python to re-execute the app and remount (double-R / Cmd+R).
    /// Deep link: Python's `Linking.addEventListener("url")` and the router receive it.
    func openURL(_ url: String) { event("url", 0, ["url": url]) }

    func devReload() { event("dev_reload", 0) }

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
        case "TextInput" where props["multiline"] as? Bool == true:
            let a = PxTextArea()
            a.onChange = { [weak self] s in
                guard let self = self else { return }
                self.typed(id, s)
                px_node_mark_dirty(self.tree, Int32(id))  // it grows with its text
                self.flush()
            }
            a.onFocus = { [weak self] in self?.event("focus", id) }
            a.onBlur = { [weak self] in self?.event("blur", id) }
            v = a
        case "TextInput":
            let t = PxTextField()
            t.addAction(UIAction { [weak self, weak t] _ in
                guard let t = t else { return }
                if t.maxLength > 0, let s = t.text, s.count > t.maxLength { t.text = String(s.prefix(t.maxLength)) }
                self?.typed(id, t.text ?? "")
            }, for: .editingChanged)
            t.addAction(UIAction { [weak self] _ in self?.event("focus", id) }, for: .editingDidBegin)
            t.addAction(UIAction { [weak self] _ in self?.event("blur", id) }, for: .editingDidEnd)
            t.addAction(UIAction { [weak self, weak t] _ in self?.event("submit_editing", id, ["value": t?.text ?? ""]) },
                        for: .editingDidEndOnExit)
            v = t
        case "Image":
            let i = UIImageView(); i.clipsToBounds = true; i.contentMode = .scaleAspectFill; v = i
        case "NativeSwitch":
            let sw = UISwitch()
            sw.addAction(UIAction { [weak self, weak sw] _ in
                guard let sw = sw else { return }
                self?.event("value_change", id, ["value": sw.isOn])
            }, for: .valueChanged)
            v = sw
        case "NativeSlider":
            let sl = UISlider()
            sl.addAction(UIAction { [weak self, weak sl] _ in
                guard let sl = sl, let self = self else { return }
                self.event("value_change", id, ["value": self.sliderValue(id, sl)])
            }, for: .valueChanged)
            sl.addAction(UIAction { [weak self, weak sl] _ in
                guard let sl = sl, let self = self else { return }
                self.event("sliding_complete", id, ["value": self.sliderValue(id, sl)])
            }, for: [.touchUpInside, .touchUpOutside, .touchCancel])
            v = sl
        case "NativeSpinner":
            let ind = UIActivityIndicatorView(style: .medium)
            ind.hidesWhenStopped = false
            ind.startAnimating()
            v = ind
        case "Path": v = PxPath()
        case "ScrollView": v = ScrollHost()
        case "NavStack":
            let n = PxNav(); n.onPop = { [weak self] in self?.event("pop_gesture", id) }; v = n
        default:
            // A view type from a linked module (`pyxpo.module_api.native_view`); otherwise a plain container.
            v = modules.makeView(type, id) { [weak self] n, val in self?.event(n, id, ["value": val ?? NSNull()]) }?.view
                ?? PxGroup()
        }
        views[id] = v
        types[id] = type
        px_node_create(tree, Int32(id))
        if Self.leaves.contains(type) || Self.controls.contains(type) { px_node_set_measured(tree, Int32(id), 1) }
        if type == "ScrollView" {
            let c = Int32(id | Self.content)
            px_node_create(tree, c)
            px_node_insert(tree, Int32(id), c, 0)
            px_node_set_num(tree, c, prop("flex_shrink"), 0)
            px_node_set_num(tree, Int32(id), prop("scroll"), 1)
            if props["horizontal"] as? Bool == true {
                px_node_set_str(tree, Int32(id), prop("flex_direction"), "row")
                px_node_set_str(tree, c, prop("flex_direction"), "row")
            }
            if let sh = v as? ScrollHost {
                sh.horizontal = props["horizontal"] as? Bool == true
                sh.onEvent = { [weak self] n, p in self?.event(n, id, p) }
                sh.onAE = { [weak self] vals in
                    var j: [String: Any] = [:]
                    for (k, x) in vals { j[String(k)] = x }
                    self?.anim.aset(j)
                }
            }
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
                let area = v as? PxTextArea
                if let cur = (v as? UITextField)?.text ?? area?.text {
                    let s = val as? String ?? ""
                    let echoed = pendingText[id]?.firstIndex(of: s)
                    if let i = echoed { pendingText[id]?.removeFirst(i + 1) }
                    // An echo of a value typed earlier is stale (newer keystrokes are on their way); anything
                    // else is the app setting the text itself.
                    if echoed == nil && cur != s {
                        pendingText[id] = nil
                        (v as? UITextField)?.text = s; area?.text = s
                        px_node_mark_dirty(tree, Int32(id))
                    }
                }
            case "placeholder":
                (v as? UITextField)?.placeholder = val as? String
                (v as? PxTextArea)?.placeholder = val as? String
            case "placeholder_color":
                if let c = Self.hexColor(val as? String) {
                    if let t = v as? UITextField {
                        t.attributedPlaceholder = NSAttributedString(string: t.placeholder ?? "", attributes: [.foregroundColor: c])
                    }
                    (v as? PxTextArea)?.placeholderColor = c
                }
            case "keyboard_type", "secure", "auto_capitalize", "auto_correct", "return_key", "max_length", "editable",
                 "auto_focus", "select_on_focus":
                applyInput(v, k, val)
            case "style": applyStyle(id, v, val as? [String: Any] ?? [:])
            case "on_press", "on_press_in", "on_press_out", "on_long_press":
                touchKeys[id, default: []].insert(k)
                if let g = v as? PxGroup, g.onTouch == nil {
                    g.isUserInteractionEnabled = true
                    g.onTouch = { [weak self] name, p in
                        var pl: [String: Any] = [:]
                        if let p = p { pl = ["x": p.x, "y": p.y] }
                        self?.event(name, id, pl)
                    }
                }
            case "on_touch_start", "on_touch_move", "on_touch_end":
                touchKeys[id, default: []].insert(k)
                if let g = v as? PxGroup, g.onRaw == nil {
                    g.onRaw = { [weak self] name, p, w in
                        self?.event(name, id, ["value": ["x": p.x, "y": p.y, "page_x": w.x, "page_y": w.y]])
                    }
                }
            case let k where k.hasPrefix("accessib"): a11yDirty = true
            case "test_id": v.accessibilityIdentifier = val as? String  // testID, as in React Native (XCUITest, Detox)
            case "on_layout": layoutListeners.insert(id)
            case "pointer_events": (v as? PxGroup)?.pointerEvents = val as? String ?? "auto"
            case "source", "resize_mode", "tint_color": if let i = v as? UIImageView { applyImage(id, i, props, removed) }
            default: if let sh = v as? ScrollHost { scrollProp(sh, k, props[k]) }
            }
        }
        if Self.controls.contains(types[id] ?? "") { applyControl(id, v, props, removed) }
        if let nv = modules.view(id) { nv.update(props.filter { $0.key != "style" }, removed.filter { $0 != "style" }) }
        for k in removed {
            if k == "on_layout" { layoutListeners.remove(id) }
            if k == "test_id" { v.accessibilityIdentifier = nil }
            if k == "pointer_events" { (v as? PxGroup)?.pointerEvents = "auto" }
            if k.hasPrefix("on_touch_") || k.hasPrefix("on_press") || k == "on_long_press" {
                // Handlers removed (e.g. a disabled Slider): stop swallowing touches.
                touchKeys[id]?.remove(k)
                let left = touchKeys[id] ?? []
                if let g = v as? PxGroup {
                    if !left.contains(where: { $0.hasPrefix("on_touch_") }) { g.onRaw = nil }
                    if !left.contains(where: { $0.hasPrefix("on_press") || $0 == "on_long_press" }) { g.onTouch = nil }
                }
            }
            if let sh = v as? ScrollHost { scrollProp(sh, k, nil) }
            if let i = v as? UIImageView, ["source", "resize_mode", "tint_color"].contains(k), props[k] == nil {
                applyImage(id, i, [:], removed)
            }
        }
        if let pv = v as? PxPath {
            if let c = props["path"] as? [[Any]] {
                pv.setCommands(c.map { $0.map { ($0 as? NSNumber)?.doubleValue ?? 0 } })
            } else if removed.contains("path") { pv.setCommands([]) }
            if let b = props["viewbox"] as? NSNumber { pv.setBox(CGFloat(b.doubleValue)) }
            if let w = props["stroke_width"] as? NSNumber { pv.strokeWidth = CGFloat(w.doubleValue) }
            if props["stroke"] != nil || props["fill"] != nil || removed.contains("stroke") || removed.contains("fill") {
                if let n = props["stroke"] as? NSNumber { pv.strokeColorCache = Self.color(n.uint32Value) }
                else if removed.contains("stroke") { pv.strokeColorCache = nil }
                if let n = props["fill"] as? NSNumber { pv.fillColorCache = Self.color(n.uint32Value) }
                else if removed.contains("fill") { pv.fillColorCache = nil }
                pv.setColors(stroke: pv.strokeColorCache, fill: pv.fillColorCache)
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
    private var layoutListeners = Set<Int>()
    private var touchKeys: [Int: Set<String>] = [:]  // live on_press*/on_touch_* props per view
    private var imgReq: [Int: String] = [:]
    private let images = Images()

    private func scrollProp(_ s: ScrollHost, _ k: String, _ val: Any?) {
        switch k {
        case "paging_enabled": s.isPagingEnabled = val as? Bool ?? false
        case "scroll_enabled": s.isScrollEnabled = val as? Bool ?? true
        case "shows_scroll_indicator":
            let on = val as? Bool ?? true
            s.showsVerticalScrollIndicator = on; s.showsHorizontalScrollIndicator = on
        case "bounces": s.bounces = val as? Bool ?? true
        case "keyboard_dismiss_mode":
            let m = val as? String
            s.keyboardDismissMode = m == "on-drag" ? .onDrag : m == "interactive" ? .interactive : .none
        case "scroll_event_throttle": s.throttle = (val as? NSNumber).map { $0.doubleValue / 1000 } ?? 0.016
        case "on_scroll":
            let o = val as? [String: Any]
            s.ae = (o?["$ae"] as? [String: Any])?.compactMapValues { ($0 as? NSNumber)?.intValue }
            s.emit = o.map { $0["emit"] as? Bool ?? false } ?? (val as? Bool == true)
        case "on_scroll_begin_drag": s.onBegin = val != nil
        case "on_scroll_end_drag": s.onEnd = val != nil
        case "on_momentum_scroll_end": s.onMomentum = val != nil
        default: break
        }
    }

    private func sliderValue(_ id: Int, _ s: UISlider) -> Double {
        var v = Double(s.value)
        let lo = Double(s.minimumValue)
        let step = (ctl[id]?["step"] as? NSNumber)?.doubleValue ?? 0
        if step > 0 { v = lo + ((v - lo) / step).rounded() * step }
        return min(max(v, lo), Double(s.maximumValue))
    }

    /// Merges props into the control's config and applies it (same prop contract as Android PxControls).
    private func applyControl(_ id: Int, _ v: UIView, _ props: [String: Any], _ removed: [String]) {
        var c = ctl[id] ?? [:]
        for k in removed { c.removeValue(forKey: k) }
        for (k, val) in props { c[k] = val }
        ctl[id] = c
        func color(_ k: String) -> UIColor? { (c[k] as? NSNumber).map { Self.color($0.uint32Value) } }
        func dbl(_ k: String, _ d: Double) -> Double { (c[k] as? NSNumber)?.doubleValue ?? d }
        if props["disabled"] != nil || removed.contains("disabled") {
            (v as? UIControl)?.isEnabled = !((c["disabled"] as? Bool) ?? false)
        }
        switch v {
        case let sw as UISwitch:
            let on = (c["value"] as? Bool) ?? false
            if sw.isOn != on { sw.setOn(on, animated: true) }
            if Self.macIdiom {
                // The Mac idiom throws on switch track and thumb colors; only the accent can change.
                sw.tintColor = color("track_on")
            } else {
                sw.onTintColor = color("track_on")
                sw.thumbTintColor = color("thumb_on") ?? color("thumb_off")
                sw.backgroundColor = color("track_off")
                sw.layer.cornerRadius = 15.5
            }
        case let sl as UISlider:
            sl.minimumValue = Float(dbl("minimum", 0))
            sl.maximumValue = Float(dbl("maximum", 1))
            if !sl.isTracking { sl.value = Float(dbl("value", Double(sl.minimumValue))) }
            if Self.macIdiom {
                // The Mac idiom throws on slider track and thumb colors; the filled track follows tintColor.
                sl.tintColor = color("min_track_color")
            } else {
                sl.minimumTrackTintColor = color("min_track_color")
                sl.maximumTrackTintColor = color("max_track_color")
                sl.thumbTintColor = color("thumb_color")
            }
        case let ind as UIActivityIndicatorView:
            ind.color = color("color")
            if (c["animating"] as? Bool) == false { ind.stopAnimating() } else { ind.startAnimating() }
        default: break
        }
    }

    private func applyImage(_ id: Int, _ v: UIImageView, _ props: [String: Any], _ removed: [String]) {
        if props["resize_mode"] != nil || removed.contains("resize_mode") {
            switch props["resize_mode"] as? String ?? "cover" {
            case "contain": v.contentMode = .scaleAspectFit
            case "stretch": v.contentMode = .scaleToFill
            case "center": v.contentMode = .center
            default: v.contentMode = .scaleAspectFill
            }
        }
        if props["tint_color"] != nil || removed.contains("tint_color") || props["source"] != nil {
            let t = props["tint_color"] as? NSNumber
            v.tintColor = t.map { Self.color($0.uint32Value) }
            v.image = v.image?.withRenderingMode(t == nil ? .alwaysOriginal : .alwaysTemplate)
        }
        if props["source"] != nil || removed.contains("source") {
            let uri = (props["source"] as? [String: Any])?["uri"] as? String ?? ""
            if uri.isEmpty {
                imgReq.removeValue(forKey: id); v.image = nil; px_node_mark_dirty(tree, Int32(id))
            } else if imgReq[id] != uri {
                imgReq[id] = uri
                let tinted = v.tintColor != nil && (props["tint_color"] != nil)
                // after this batch, so a new view has its frame. A frame with both sides set is the display size
                // (a view the engine sizes from the image is 0 on a side until it loads, so it gets the image whole).
                DispatchQueue.main.async { [weak self, weak v] in
                    guard let self = self, let v = v, self.imgReq[id] == uri, self.views[id] === v else { return }
                    let s = v.window?.screen.scale ?? UIScreen.main.scale
                    let fit = v.contentMode != .center && v.bounds.width >= 1 && v.bounds.height >= 1
                    let px = fit ? CGSize(width: v.bounds.width * s, height: v.bounds.height * s) : .zero
                    self.images.load(uri, px: px) { [weak self, weak v] img, err in
                        guard let self = self, let v = v, self.imgReq[id] == uri else { return }
                        if let img = img {
                            v.image = tinted ? img.withRenderingMode(.alwaysTemplate) : img
                            px_node_mark_dirty(self.tree, Int32(id))
                            self.flush()
                            self.event("load", id, ["value": ["width": Double(img.size.width), "height": Double(img.size.height)]])
                        } else { self.event("error", id, ["value": ["message": err ?? "error"]]) }
                    }
                }
            }
        }
    }

    private func scrollTo(_ id: Int, _ x: Double?, _ y: Double?, _ animated: Bool) {
        guard let s = views[id] as? ScrollHost else { return }
        let maxX = max(0, s.contentSize.width - s.bounds.width), maxY = max(0, s.contentSize.height - s.bounds.height)
        let horiz = s.horizontal
        // scroll_to_end in RTL: the end of a horizontal list is its left edge
        let tx = x.map { CGFloat($0) } ?? (horiz ? (rtl ? 0 : maxX) : s.contentOffset.x)
        let ty = y.map { CGFloat($0) } ?? (horiz ? s.contentOffset.y : maxY)
        s.setContentOffset(CGPoint(x: min(max(0, tx), maxX), y: min(max(0, ty), maxY)), animated: animated)
    }

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
        case "button", "imagebutton", "menuitem", "tab": tr.insert(.button)
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

    private func insert(_ parent0: Int, _ id: Int, _ index0: Int) {
        // Modals live on the root so they cover the whole screen whatever their Python parent is.
        let parent = types[id] == "Modal" ? 1 : parent0
        let index = parent == parent0 ? index0 : Int(Int32.max)
        guard let g = groupOf(parent), let v = views[id] else { return }
        v.removeFromSuperview()
        g.insertSubview(v, at: min(index, g.subviews.count))
        if types[id] == "Modal" { g.bringSubviewToFront(v) }
        if let n = g as? PxNav, v.superview === n { n.pushed(v) }
        px_node_remove(tree, parentNode(parent), Int32(id))
        px_node_insert(tree, parentNode(parent), Int32(id), Int32(index))
    }

    private func remove(_ parent0: Int, _ id: Int) {
        let parent = types[id] == "Modal" ? 1 : parent0
        if let v = views[id] {
            if let n = groupOf(parent) as? PxNav, n.popped(v) {} else { v.removeFromSuperview() }  // popping screen leaves when its animation ends
        }
        px_node_remove(tree, parentNode(parent), Int32(id))
    }

    private func delete(_ id: Int) {
        if let v = views.removeValue(forKey: id) {
            if !((v.superview as? PxNav)?.lingering.contains(v) ?? false) { v.removeFromSuperview() }
        }
        binds.removeValue(forKey: id)
        modules.dropView(id)
        layoutListeners.remove(id); imgReq.removeValue(forKey: id); touchKeys.removeValue(forKey: id); pendingText[id] = nil
        if types.removeValue(forKey: id) == "ScrollView" { px_node_delete(tree, Int32(id | Self.content)) }
        px_node_delete(tree, Int32(id))
        styles.removeValue(forKey: id)
        pads.removeValue(forKey: id)
        boxes.removeValue(forKey: id)
        texts.removeValue(forKey: id)
        ctl.removeValue(forKey: id)
        spans.removeValue(forKey: id)
        a11y.removeValue(forKey: id)
    }

    // -- TextInput -----------------------------------------------------------------------------------
    static func hexColor(_ s: String?) -> UIColor? {
        guard var h = s?.trimmingCharacters(in: .whitespaces), h.hasPrefix("#") else { return nil }
        h.removeFirst()
        if h.count == 3 { h = h.map { "\($0)\($0)" }.joined() }
        guard let n = UInt32(h, radix: 16), h.count == 6 else { return nil }
        return UIColor(red: CGFloat((n >> 16) & 255) / 255, green: CGFloat((n >> 8) & 255) / 255,
                       blue: CGFloat(n & 255) / 255, alpha: 1)
    }

    /// Records a value the user typed (see `pendingText`) and reports it.
    private func typed(_ id: Int, _ s: String) {
        var q = pendingText[id] ?? []
        q.append(s); if q.count > 256 { q.removeFirst() }
        pendingText[id] = q
        event("change_text", id, ["value": s])
    }

    /// Input props for a single-line PxTextField or a multiline PxTextArea (its UITextView takes the traits).
    private func applyInput(_ v: UIView, _ k: String, _ val: Any) {
        let t = v as? PxTextField, a = v as? PxTextArea
        let tv = a?.field
        switch k {
        case "keyboard_type":
            let kt: UIKeyboardType
            switch val as? String ?? "default" {
            case "number", "number-pad", "numeric": kt = .numberPad
            case "decimal", "decimal-pad": kt = .decimalPad
            case "phone", "phone-pad": kt = .phonePad
            case "email", "email-address": kt = .emailAddress
            case "url": kt = .URL
            default: kt = .default
            }
            t?.keyboardType = kt; tv?.keyboardType = kt
        case "secure": t?.isSecureTextEntry = val as? Bool ?? false
        case "auto_capitalize":
            let ac: UITextAutocapitalizationType
            switch val as? String ?? "none" {
            case "sentences": ac = .sentences
            case "words": ac = .words
            case "characters": ac = .allCharacters
            default: ac = .none
            }
            t?.autocapitalizationType = ac; tv?.autocapitalizationType = ac
        case "auto_correct":
            let ac: UITextAutocorrectionType = (val as? Bool ?? true) ? .yes : .no
            t?.autocorrectionType = ac; tv?.autocorrectionType = ac
        case "return_key":
            let rk: UIReturnKeyType
            switch val as? String ?? "done" {
            case "go": rk = .go
            case "next": rk = .next
            case "search": rk = .search
            case "send": rk = .send
            default: rk = .done
            }
            t?.returnKeyType = rk  // a multiline field's return key adds a line
        case "max_length": t?.maxLength = val as? Int ?? 0; a?.maxLength = val as? Int ?? 0
        case "editable": t?.isEnabled = val as? Bool ?? true; tv?.isEditable = val as? Bool ?? true
        case "select_on_focus": t?.selectOnFocus = val as? Bool ?? false; a?.selectOnFocus = val as? Bool ?? false
        case "auto_focus":
            if val as? Bool == true {
                DispatchQueue.main.async { _ = t?.becomeFirstResponder(); _ = tv?.becomeFirstResponder() }
            }
        default: break
        }
    }

    // -- native modules ------------------------------------------------------------------------------
    private func reply(_ id: Int, _ value: Any?, error: String? = nil) {
        if let e = error { event("call_result", id, ["error": e]) }
        else { event("call_result", id, ["value": value ?? NSNull()]) }
    }

    private func call(_ id: Int, _ module: String, _ method: String, _ args: [Any], _ wantReply: Bool) {
        switch "\(module).\(method)" {
        case "Scroll.to":
            scrollTo(args[0] as? Int ?? 0, (args[1] as? NSNumber)?.doubleValue, (args[2] as? NSNumber)?.doubleValue,
                     args.count > 3 ? args[3] as? Bool ?? true : true)
        case "Scroll.to_end": scrollTo(args[0] as? Int ?? 0, nil, nil, args.count > 1 ? args[1] as? Bool ?? true : true)
        case "StatusBar.set_hidden":
            PxRootViewController.shared?.setBarHidden((args.first as? Bool) ?? false)
        case "StatusBar.set_style":
            PxRootViewController.shared?.setBarStyle(light: (args.first as? String) == "light")
        case "Back.set_enabled", "Back.exit": break  // iOS has no hardware back
        case "Keyboard.dismiss":
            UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
        case "Clipboard.set_string": UIPasteboard.general.string = args.first as? String ?? ""
        case "Clipboard.get_string": if wantReply { reply(id, UIPasteboard.general.string ?? ""); return }
        case "Linking.open_url":
            if let u = URL(string: args.first as? String ?? "") { UIApplication.shared.open(u) }
        case "SplashScreen.prevent_auto_hide": splash.preventAutoHide()
        case "SplashScreen.hide": splash.hide()
        case "I18nManager.set_rtl": setRTL((args.first as? Bool) ?? false)
        case "Vibration.vibrate": AudioServicesPlaySystemSound(kSystemSoundID_Vibrate)
        case "Alert.alert":
            let labels = (args.count > 2 ? args[2] as? [String] : nil) ?? ["OK"]
            let a = UIAlertController(title: args.first as? String, message: args.count > 1 ? args[1] as? String : nil,
                                      preferredStyle: .alert)
            for (i, l) in labels.enumerated() {
                a.addAction(UIAlertAction(title: l, style: .default) { [weak self] _ in
                    if wantReply { self?.reply(id, i) }
                })
            }
            var top = root.window?.rootViewController
            while let p = top?.presentedViewController { top = p }
            top?.present(a, animated: true)
            return
        default:
            if modules.call(module, method, args, { [weak self] v, e in
                if wantReply { self?.reply(id, v, error: e) }
            }) { return }
            if wantReply { reply(id, nil, error: "unknown native call \(module).\(method) (is native module '\(module)' listed in [tool.pyxpo] modules?)") }
            return
        }
        if wantReply { reply(id, nil) }
    }

    // -- style ---------------------------------------------------------------------------------------
    private func prop(_ name: String) -> Int32 {
        if let p = propIds[name] { return p }
        let p = px_prop_id(name)
        propIds[name] = p
        return p
    }

    private func animVal(_ k: String, _ node: Int) -> NSNumber {
        let x = anim.resolve(node)
        if k == "color" || k.hasSuffix("_color") { return NSNumber(value: UInt32(x)) }
        return NSNumber(value: x)
    }

    /// Replaces `{"$a": node}` bindings with the node's current value and records the bindings for the frame loop.
    private func resolveBinds(_ id: Int, _ s: [String: Any]) -> [String: Any] {
        var b: [String: Int] = [:]
        for (k, o) in s { if let m = o as? [String: Any], let n = m["$a"] as? Int { b[k] = n } }
        if b.isEmpty { binds.removeValue(forKey: id); return s }
        var out = s
        for (k, n) in b { out[k] = animVal(k, n) }
        binds[id] = b
        return out
    }

    private func depsOf(_ node: Int) -> Set<Int> {
        if let d = depCache[node] { return d }
        var d = Set<Int>()
        anim.deps(node, &d)
        depCache[node] = d
        return d
    }

    private static let transformKeys: Set<String> = ["opacity", "rotate", "scale", "scale_x", "scale_y", "translate_x", "translate_y"]

    /// Per-frame: write the changed animated values straight onto views. Layout keys re-run the engine once.
    private func onAnimFrame(_ touched: Set<Int>) {
        var relayout = false
        for (id, b) in binds {
            guard let v = views[id], var s = styles[id] else { continue }
            var tr = false, box = false, txt = false
            for (k, n) in b where !touched.isDisjoint(with: depsOf(n)) {
                let nv = animVal(k, n)
                s[k] = nv
                if Self.transformKeys.contains(k) { tr = true }
                else if k == "color" { txt = true }
                else if k.hasPrefix("shadow") || k == "elevation" || k.hasPrefix("background") || k.hasPrefix("border") {
                    box = true
                    if prop(k) >= 0 { px_node_set_num(tree, Int32(id), prop(k), nv.floatValue); px_node_mark_dirty(tree, Int32(id)); relayout = true }
                } else if prop(k) >= 0 {
                    px_node_set_num(tree, Int32(id), prop(k), nv.floatValue)
                    px_node_mark_dirty(tree, Int32(id))
                    relayout = true
                }
            }
            styles[id] = s
            if tr { paintTransform(v, s) }
            if box { paintBox(id, v, s) }
            if txt { paintText(id, v, s) }
        }
        if relayout { flush() }
    }

    private func applyStyle(_ id: Int, _ v: UIView, _ raw: [String: Any]) {
        let s = resolveBinds(id, raw)
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
        v.isHidden = (s["display"] as? String) == "none"
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
            (v as? PxTextArea)?.insets = p
            (v as? UIButton)?.contentEdgeInsets = p
        }
        paintBox(id, v, s)
        paintTransform(v, s)
        paintText(id, v, s)
    }

    private func paintTransform(_ v: UIView, _ s: [String: Any]) {
        v.alpha = min(max(num(s, "opacity", 1), 0), 1)
        let sc = num(s, "scale", 1)
        v.transform = CGAffineTransform(translationX: num(s, "translate_x"), y: num(s, "translate_y"))
            .rotated(by: num(s, "rotate") * .pi / 180)
            .scaledBy(x: sc * num(s, "scale_x", 1), y: sc * num(s, "scale_y", 1))
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
        if v is UIImageView || modules.view(id) != nil {
            // The picture (or a module view's own drawing, a whiteboard's ink) is the layer's contents, which every
            // sublayer covers: paint the fill on the layer itself (drawn under the contents), and clip to the
            // corners as React Native does for images.
            v.layer.backgroundColor = spec.bg?.cgColor
            spec.bg = nil
            spec.clip = spec.clip || spec.radii.contains { $0 > 0 }
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
        v.clipsToBounds = v is UIScrollView || (spec.clip && !spec.radii.contains { $0 > 0 })  // a scroll view always clips its content
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
        para.alignment = textAlign(s)
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

    /// left/right are start/end: swapped in RTL, as in React Native.
    private func textAlign(_ s: [String: Any]) -> NSTextAlignment {
        switch s["text_align"] as? String {
        case "center": return .center
        case "justify": return .justified
        case "right": return rtl ? .left : .right
        default: return rtl ? .right : .natural
        }
    }

    /// Mirrors the layout. Frames move at the next flush; text alignment and scroll positions follow here.
    private func setRTL(_ on: Bool) {
        if on == rtl { return }
        rtl = on
        px_tree_set_rtl(tree, on ? 1 : 0)
        root.semanticContentAttribute = on ? .forceRightToLeft : .forceLeftToRight
        for (id, s) in styles { if let v = views[id] { paintText(id, v, s) } }
        for (id, t) in types where Self.leaves.contains(t) { px_node_mark_dirty(tree, Int32(id)) }
        flush()
        for case let sh as ScrollHost in views.values where sh.horizontal { sh.toStart(rtl: on) }
    }

    private func paintText(_ id: Int, _ v: UIView, _ s: [String: Any]) {
        guard v is UILabel || v is UIButton || v is UITextField || v is PxTextArea else { return }
        let font = Self.uiFont(s)
        let c = col(s, "color")
        let align = textAlign(s)
        if let l = v as? UILabel {
            renderLabel(id, l, s)
        } else if let b = v as? UIButton {
            b.titleLabel?.font = font
            b.setTitleColor(c, for: .normal)
        } else if let t = v as? UITextField {
            t.font = font
            t.textColor = c ?? .label
            t.textAlignment = align
        } else if let a = v as? PxTextArea {
            a.font = font
            a.field.textColor = c ?? .label
            a.field.textAlignment = align
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
        else if let a = v as? PxTextArea { s = CGSize(width: 0, height: a.contentHeight(lw == inf ? 10000 : lw)) }
        else if let i = v as? UIImageView { s = i.image?.size ?? .zero }
        else if v is UISwitch { s = v.sizeThatFits(.zero) }
        else if v is UISlider { s = CGSize(width: 0, height: 31) }
        else if let a = v as? UIActivityIndicatorView { s = a.intrinsicContentSize }
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
                             dark: root.traitCollection.userInterfaceStyle == .dark,
                             insets: root.safeAreaInsets, keyboard: kbHeight, startup: false)
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
                    let old = sh.contentSize
                    sh.content.frame = CGRect(origin: .zero, size: r.size)
                    sh.contentSize = r.size
                    if rtl && sh.horizontal { sh.keepRightEdge(was: old) }
                }
            } else {
                if layoutListeners.contains(id) {
                    event("layout", id, ["value": ["x": Double(r.minX), "y": Double(r.minY),
                                                   "width": Double(r.width), "height": Double(r.height)]])
                }
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
