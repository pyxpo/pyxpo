import UIKit

/// Per-view layout hints (any UIView can be a flex child).
final class PxExtra {
    var flex: CGFloat = 0
    var margin: CGFloat = 0
    var width: CGFloat = -1   // -1 = auto
    var height: CGFloat = -1
}

private var extraKey: UInt8 = 0

extension UIView {
    var px: PxExtra {
        if let e = objc_getAssociatedObject(self, &extraKey) as? PxExtra { return e }
        let e = PxExtra()
        objc_setAssociatedObject(self, &extraKey, e, .OBJC_ASSOCIATION_RETAIN_NONATOMIC)
        return e
    }
}

/// Size of a child given the space offered. nil max = unbounded. exact = fill the offered size.
func pxChildSize(_ v: UIView, maxW: CGFloat?, maxH: CGFloat?, exactW: Bool, exactH: Bool) -> CGSize {
    var mw = maxW, mh = maxH, ew = exactW, eh = exactH
    if v.px.width >= 0 { mw = v.px.width; ew = true }
    if v.px.height >= 0 { mh = v.px.height; eh = true }
    var s: CGSize
    if let l = v as? PyxpoView {
        s = l.measure(maxW: mw, maxH: mh, exactW: ew, exactH: eh)
    } else if let sc = v as? ScrollHost {
        s = sc.measure(maxW: mw, maxH: mh, exactW: ew, exactH: eh)
    } else {
        s = v.sizeThatFits(CGSize(width: mw ?? 10000, height: mh ?? 10000))
        if let w = mw, s.width > w { s.width = w }
        if let h = mh, s.height > h { s.height = h }
    }
    if ew, let w = mw { s.width = w }
    if eh, let h = mh { s.height = h }
    return s
}

/// Flexbox subset: flex_direction, flex, gap, padding, margin, align_items, justify_content, width, height.
final class PyxpoView: UIView {
    var row = false
    var gap: CGFloat = 0
    var alignItems = "stretch"   // stretch | start | center | end
    var justify = "start"        // start | center | end | space_between
    var padding: CGFloat = 0

    private var kids: [UIView] { subviews.filter { !$0.isHidden } }

    private struct Plan { var sizes: [CGSize]; var used: CGFloat; var cross: CGFloat }

    private func plan(maxW: CGFloat?, maxH: CGFloat?, exactW: Bool, exactH: Bool) -> Plan {
        let ks = kids
        let innerW = maxW.map { max(0, $0 - 2 * padding) }
        let innerH = maxH.map { max(0, $0 - 2 * padding) }
        let mainMax = row ? innerW : innerH
        let crossMax = row ? innerH : innerW
        let crossExact = row ? exactH : exactW
        let stretch = alignItems == "stretch" && crossExact && crossMax != nil
        var sizes = [CGSize](repeating: .zero, count: ks.count)
        var used = gap * CGFloat(max(0, ks.count - 1))
        var cross: CGFloat = 0
        var totalGrow: CGFloat = 0

        func ask(_ k: UIView, main: CGFloat?, mainExact: Bool, m: CGFloat) -> CGSize {
            let crossAvail = crossMax.map { max(0, $0 - m) }
            return row
                ? pxChildSize(k, maxW: main, maxH: crossAvail, exactW: mainExact, exactH: stretch)
                : pxChildSize(k, maxW: crossAvail, maxH: main, exactW: stretch, exactH: mainExact)
        }
        for (i, k) in ks.enumerated() {
            let m = k.px.margin * 2
            if k.px.flex > 0 && mainMax != nil { totalGrow += k.px.flex; used += m; continue }
            let s = ask(k, main: mainMax.map { max(0, $0 - used - m) }, mainExact: false, m: m)
            sizes[i] = s
            used += (row ? s.width : s.height) + m
            cross = max(cross, (row ? s.height : s.width) + m)
        }
        if let mm = mainMax, totalGrow > 0 {
            let remaining = max(0, mm - used)
            for (i, k) in ks.enumerated() where k.px.flex > 0 {
                let m = k.px.margin * 2
                let share = (remaining * k.px.flex / totalGrow).rounded()
                let s = ask(k, main: share, mainExact: true, m: m)
                sizes[i] = s
                used += share
                cross = max(cross, (row ? s.height : s.width) + m)
            }
        }
        return Plan(sizes: sizes, used: used, cross: cross)
    }

    func measure(maxW: CGFloat?, maxH: CGFloat?, exactW: Bool, exactH: Bool) -> CGSize {
        let p = plan(maxW: maxW, maxH: maxH, exactW: exactW, exactH: exactH)
        var w = (row ? p.used : p.cross) + 2 * padding
        var h = (row ? p.cross : p.used) + 2 * padding
        if let mw = maxW { w = exactW ? mw : min(w, mw) }
        if let mh = maxH { h = exactH ? mh : min(h, mh) }
        return CGSize(width: w, height: h)
    }

    override func sizeThatFits(_ size: CGSize) -> CGSize {
        measure(maxW: size.width, maxH: size.height, exactW: false, exactH: false)
    }

    override func layoutSubviews() {
        let ks = kids
        let b = bounds.size
        let p = plan(maxW: b.width, maxH: b.height, exactW: true, exactH: true)
        let innerW = b.width - 2 * padding, innerH = b.height - 2 * padding
        let mainSize = row ? innerW : innerH
        let crossSize = row ? innerH : innerW
        var total = gap * CGFloat(max(0, ks.count - 1))
        for (i, k) in ks.enumerated() { total += (row ? p.sizes[i].width : p.sizes[i].height) + k.px.margin * 2 }
        let extra = max(0, mainSize - total)
        var pos: CGFloat = justify == "center" ? extra / 2 : (justify == "end" ? extra : 0)
        let between: CGFloat = justify == "space_between" && ks.count > 1 ? extra / CGFloat(ks.count - 1) : 0
        for (i, k) in ks.enumerated() {
            let m = k.px.margin
            let s = p.sizes[i]
            let kMain = row ? s.width : s.height
            let kCross = row ? s.height : s.width
            let cOff: CGFloat
            switch alignItems {
            case "center": cOff = (crossSize - kCross) / 2
            case "end": cOff = crossSize - kCross - m
            default: cOff = m
            }
            let x = padding + (row ? pos + m : cOff)
            let y = padding + (row ? cOff : pos + m)
            k.frame = CGRect(x: x.rounded(), y: y.rounded(), width: s.width.rounded(), height: s.height.rounded())
            pos += kMain + m * 2 + gap + between
        }
    }
}

/// ScrollView: a UIScrollView whose content is a PyxpoView laid out with unbounded height.
final class ScrollHost: UIScrollView {
    let content = PyxpoView()

    override init(frame: CGRect) {
        super.init(frame: frame)
        addSubview(content)
    }
    required init?(coder: NSCoder) { fatalError() }

    func measure(maxW: CGFloat?, maxH: CGFloat?, exactW: Bool, exactH: Bool) -> CGSize {
        let w = maxW ?? 320
        let c = content.measure(maxW: w, maxH: nil, exactW: true, exactH: false)
        let h = maxH.map { exactH ? $0 : min(c.height, $0) } ?? c.height
        return CGSize(width: w, height: h)
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        let c = content.measure(maxW: bounds.width, maxH: nil, exactW: true, exactH: false)
        content.frame = CGRect(x: 0, y: 0, width: bounds.width, height: c.height)
        contentSize = c
    }
}
