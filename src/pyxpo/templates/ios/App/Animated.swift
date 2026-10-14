import UIKit

/// Native animation driver. Swift port of pyxpo/animated/engine.py (the reference); numbers are pinned by
/// tests/data/anim_golden.json. One CADisplayLink (common run-loop mode, paused when idle) evaluates every running
/// animation per frame on the main thread and hands the changed value ids to `onFrame`, which writes view
/// properties directly. No Python per frame.
final class Animated {
    typealias J = [String: Any]
    private let emit: (String, Int, J) -> Void
    private let onFrame: (Set<Int>) -> Void

    init(emit: @escaping (String, Int, J) -> Void, onFrame: @escaping (Set<Int>) -> Void) {
        self.emit = emit
        self.onFrame = onFrame
    }

    // -- helpers -------------------------------------------------------------------------------------
    private static func d(_ o: Any?, _ def: Double = 0) -> Double { (o as? NSNumber)?.doubleValue ?? def }
    private static func i(_ o: Any?) -> Int { (o as? NSNumber)?.intValue ?? 0 }
    private static func arr(_ o: Any?) -> [Double] { (o as? [Any] ?? []).map { d($0) } }

    // -- easing --------------------------------------------------------------------------------------
    private static func bezier(_ x1: Double, _ y1: Double, _ x2: Double, _ y2: Double) -> (Double) -> Double {
        func coord(_ a: Double, _ b: Double, _ t: Double) -> Double {
            let u = 1 - t
            return 3 * u * u * t * a + 3 * u * t * t * b + t * t * t
        }
        return { x in
            if x <= 0 { return 0 }
            if x >= 1 { return 1 }
            var lo = 0.0, hi = 1.0, t = x
            for _ in 0..<40 {
                let cx = coord(x1, x2, t)
                if abs(cx - x) < 1e-7 { break }
                if cx < x { lo = t } else { hi = t }
                t = (lo + hi) / 2
            }
            return coord(y1, y2, t)
        }
    }

    private static func bounce(_ t0: Double) -> Double {
        var t = t0
        if t < 1 / 2.75 { return 7.5625 * t * t }
        if t < 2 / 2.75 { t -= 1.5 / 2.75; return 7.5625 * t * t + 0.75 }
        if t < 2.5 / 2.75 { t -= 2.25 / 2.75; return 7.5625 * t * t + 0.9375 }
        t -= 2.625 / 2.75
        return 7.5625 * t * t + 0.984375
    }

    static func easing(_ spec: J?) -> (Double) -> Double {
        guard let spec = spec else { return easing(["e": "in_out", "f": ["e": "quad"]]) }
        switch spec["e"] as? String ?? "" {
        case "linear": return { $0 }
        case "ease": return bezier(0.42, 0, 1, 1)
        case "quad": return { $0 * $0 }
        case "cubic": return { $0 * $0 * $0 }
        case "poly": let n = d(spec["n"], 4); return { pow($0, n) }
        case "sin": return { 1 - cos($0 * Double.pi / 2) }
        case "circle": return { 1 - sqrt(max(0, 1 - $0 * $0)) }
        case "exp": return { pow(2, 10 * ($0 - 1)) }
        case "elastic": let p = d(spec["b"], 1) * Double.pi; return { 1 - pow(cos($0 * Double.pi / 2), 3) * cos($0 * p) }
        case "back": let s = d(spec["s"], 1.70158); return { $0 * $0 * (($0 * (s + 1)) - s) }
        case "bounce": return { bounce($0) }
        case "bezier": let p = arr(spec["p"]); return bezier(p[0], p[1], p[2], p[3])
        case "in": return easing(spec["f"] as? J)
        case "out": let f = easing(spec["f"] as? J); return { 1 - f(1 - $0) }
        case "in_out":
            let f = easing(spec["f"] as? J)
            return { $0 < 0.5 ? f(2 * $0) / 2 : 1 - f(2 * (1 - $0)) / 2 }
        default: return { $0 }
        }
    }

    // -- node graph ----------------------------------------------------------------------------------
    private enum N {
        case value
        case interp(src: Int, inp: [Double], out: [Double], left: String, right: String, color: Bool, ease: ((Double) -> Double)?)
        case bin(add: Bool, a: Int, b: Int)
    }

    private var nodes: [Int: N] = [:]
    private var values: [Int: Double] = [:]
    private var vel: [Int: Double] = [:]
    private var prev: [Int: (Double, Double)] = [:]      // t, v
    private var listen = Set<Int>()
    private var lastSent: [Int: Double] = [:]
    private var anims: [(id: Int, run: Run, nodes: Set<Int>)] = []
    private var link: CADisplayLink?

    func anode(_ id: Int, _ o: J) {
        switch o["t"] as? String ?? "" {
        case "value": nodes[id] = .value; values[id] = Self.d(o["v"])
        case "interp":
            let ex = o["ex"] as? [String] ?? ["extend", "extend"]
            nodes[id] = .interp(src: Self.i(o["src"]), inp: Self.arr(o["in"]), out: Self.arr(o["out"]), left: ex[0],
                                right: ex[1], color: o["color"] as? Bool ?? false,
                                ease: (o["easing"] as? J).map { Self.easing($0) })
        case "add": nodes[id] = .bin(add: true, a: Self.i(o["a"]), b: Self.i(o["b"]))
        case "mul": nodes[id] = .bin(add: false, a: Self.i(o["a"]), b: Self.i(o["b"]))
        default: break
        }
    }

    func anodeDel(_ id: Int) {
        stopTouching([id], false)
        nodes[id] = nil; values[id] = nil; vel[id] = nil; prev[id] = nil; lastSent[id] = nil; listen.remove(id)
    }

    func alisten(_ id: Int, _ on: Bool) {
        if on { listen.insert(id); lastSent[id] = values[id] ?? 0 } else { listen.remove(id) }
    }

    func astop(_ aid: Int) {
        if let k = anims.firstIndex(where: { $0.id == aid }) {
            let r = anims.remove(at: k)
            emitEnd(aid, false, r.nodes)
        }
    }

    func aset(_ vals: J) {
        let ids = Set(vals.keys.compactMap { Int($0) })
        stopTouching(ids, false)
        for id in ids { values[id] = Self.d(vals[String(id)]); vel[id] = 0; prev[id] = nil }
        valueEvents(ids)
        onFrame(ids)
    }

    func animate(_ aid: Int, _ spec: J) {
        let ns = nodesOf(spec)
        stopTouching(ns, false)
        anims.append((aid, build(spec), ns))
        start()
    }

    func resolve(_ id: Int) -> Double {
        guard let n = nodes[id] else { return 0 }
        switch n {
        case .value: return values[id] ?? 0
        case let .interp(src, _, _, _, _, _, _): return interpolate(resolve(src), n)
        case let .bin(add, a, b): return add ? resolve(a) + resolve(b) : resolve(a) * resolve(b)
        }
    }

    /// Value-node ids a node depends on (itself if it is a value).
    func deps(_ id: Int, _ out: inout Set<Int>) {
        guard let n = nodes[id] else { return }
        switch n {
        case .value: out.insert(id)
        case let .interp(src, _, _, _, _, _, _): deps(src, &out)
        case let .bin(_, a, b): deps(a, &out); deps(b, &out)
        }
    }

    private func lerpColor(_ a: UInt32, _ b: UInt32, _ f: Double) -> Double {
        var out: UInt32 = 0
        for shift in [24, 16, 8, 0] as [UInt32] {
            let ca = Double((a >> shift) & 255), cb = Double((b >> shift) & 255)
            let v = min(255, max(0, (ca + (cb - ca) * f).rounded(.toNearestOrEven)))
            out |= UInt32(v) << shift
        }
        return Double(out)
    }

    private func interpolate(_ x: Double, _ node: N) -> Double {
        guard case let .interp(_, inp, out, left, right, color, ease) = node else { return x }
        let len = inp.count
        var i: Int
        if x < inp[0] {
            if left == "clamp" { return out[0] }
            if left == "identity" { return x }
            i = 0
        } else if x > inp[len - 1] {
            if right == "clamp" { return out[len - 1] }
            if right == "identity" { return x }
            i = len - 2
        } else {
            i = 0
            while i < len - 2 && x > inp[i + 1] { i += 1 }
        }
        let a = inp[i], b = inp[i + 1]
        var f = b == a ? 0 : (x - a) / (b - a)
        if let e = ease, f >= 0 && f <= 1 { f = e(f) }
        if color { return lerpColor(UInt32(out[i]), UInt32(out[i + 1]), min(1, max(0, f))) }
        return out[i] + (out[i + 1] - out[i]) * f
    }

    /// Displacement and velocity (per second) of a damped spring dt seconds after release.
    private func springAt(_ dt: Double, _ x0: Double, _ v0: Double, _ k: Double, _ c: Double, _ m: Double) -> (Double, Double) {
        let w0 = sqrt(k / m)
        let z = c / (2 * sqrt(k * m))
        if abs(z - 1) < 1e-9 {
            let e = exp(-w0 * dt), b = v0 + w0 * x0
            return (e * (x0 + b * dt), e * (v0 - w0 * b * dt))
        }
        if z < 1 {
            let wd = w0 * sqrt(1 - z * z), e = exp(-z * w0 * dt), b = (v0 + z * w0 * x0) / wd
            let cs = cos(wd * dt), sn = sin(wd * dt)
            return (e * (x0 * cs + b * sn), e * ((b * wd - z * w0 * x0) * cs - (x0 * wd + z * w0 * b) * sn))
        }
        let s = w0 * sqrt(z * z - 1)
        let r1 = -z * w0 + s, r2 = -z * w0 - s
        let c2 = (v0 - r1 * x0) / (r2 - r1), c1 = x0 - c2
        let e1 = exp(r1 * dt), e2 = exp(r2 * dt)
        return (c1 * e1 + c2 * e2, c1 * r1 * e1 + c2 * r2 * e2)
    }

    // -- running animations --------------------------------------------------------------------------
    private func get(_ n: Int) -> Double { values[n] ?? 0 }
    private func setV(_ n: Int, _ v: Double, _ t: Double) {
        if let p = prev[n], t > p.0 { vel[n] = (v - p.1) / ((t - p.0) / 1000) }
        prev[n] = (t, v)
        values[n] = v
    }

    private class Run { func update(_ t: Double) -> Bool { true } }

    private final class Timing: Run {
        let a: Animated, s: J, node: Int, ease: (Double) -> Double
        var t0 = Double.nan, from = 0.0
        init(_ a: Animated, _ s: J) { self.a = a; self.s = s; node = Animated.i(s["node"]); ease = Animated.easing(s["easing"] as? J) }
        override func update(_ t: Double) -> Bool {
            if t0.isNaN { t0 = t; from = a.get(node); a.prev[node] = (t, from) }
            let ms = Animated.d(s["ms"]), to = Animated.d(s["to"])
            let p = ms <= 0 ? 1 : min(1, (t - t0) / ms)
            a.setV(node, p >= 1 ? to : from + (to - from) * ease(p), t)
            return p >= 1
        }
    }

    private final class Spring: Run {
        let a: Animated, s: J, node: Int
        var t0 = Double.nan, x0 = 0.0, v0 = 0.0
        init(_ a: Animated, _ s: J) { self.a = a; self.s = s; node = Animated.i(s["node"]) }
        override func update(_ t: Double) -> Bool {
            let to = Animated.d(s["to"])
            if t0.isNaN {
                t0 = t
                let cur = a.get(node)
                x0 = cur - to
                if let v = s["v0"] as? NSNumber { v0 = v.doubleValue } else { v0 = a.vel[node] ?? 0 }
                a.prev[node] = (t, cur)
            }
            let (x, v) = a.springAt((t - t0) / 1000, x0, v0, Animated.d(s["k"]), Animated.d(s["c"]), Animated.d(s["m"]))
            var done = abs(x) <= Animated.d(s["rest_d"], 0.001) && abs(v) <= Animated.d(s["rest_v"], 0.001)
            if (s["clamp"] as? Bool ?? false) && t > t0 && x0 != 0 && x * x0 <= 0 { done = true }
            if x0 == 0 && v0 == 0 { done = true }
            a.setV(node, done ? to : to + x, t)
            if done { a.vel[node] = 0 }
            return done
        }
    }

    private final class Decay: Run {
        let a: Animated, s: J, node: Int
        var t0 = Double.nan, from = 0.0, v0 = 0.0
        init(_ a: Animated, _ s: J) { self.a = a; self.s = s; node = Animated.i(s["node"]) }
        override func update(_ t: Double) -> Bool {
            let dec = Animated.d(s["decel"], 0.998)
            if t0.isNaN {
                t0 = t; from = a.get(node)
                if let v = s["v0"] as? NSNumber { v0 = v.doubleValue } else { v0 = (a.vel[node] ?? 0) / 1000 }
                a.prev[node] = (t, from)
            }
            let k = 1 - dec, dt = t - t0
            a.setV(node, from + v0 / k * (1 - exp(-k * dt)), t)
            let done = abs(v0 * exp(-k * dt)) * 16.67 < 0.1
            if done { a.vel[node] = 0 }
            return done
        }
    }

    private final class DelayRun: Run {
        let ms: Double
        var t0 = Double.nan
        init(_ ms: Double) { self.ms = ms }
        override func update(_ t: Double) -> Bool { if t0.isNaN { t0 = t }; return t - t0 >= ms }
    }

    private final class Seq: Run {
        let items: [Run]
        var i = 0
        init(_ a: Animated, _ s: J) { items = (s["items"] as? [J] ?? []).map { a.build($0) } }
        override func update(_ t: Double) -> Bool {
            while i < items.count { if !items[i].update(t) { return false }; i += 1 }
            return true
        }
    }

    private final class Par: Run {
        let items: [Run]
        var done: [Bool]
        init(_ a: Animated, _ s: J) { items = (s["items"] as? [J] ?? []).map { a.build($0) }; done = Array(repeating: false, count: items.count) }
        override func update(_ t: Double) -> Bool {
            for k in items.indices where !done[k] { done[k] = items[k].update(t) }
            return done.allSatisfy { $0 }
        }
    }

    private final class Loop: Run {
        let a: Animated, s: J
        let n: Int
        var i = 0
        var cur: Run?
        var snap: [Int: Double]?
        init(_ a: Animated, _ s: J) { self.a = a; self.s = s; n = (s["n"] as? NSNumber)?.intValue ?? -1 }
        override func update(_ t: Double) -> Bool {
            for _ in 0..<2 {
                if cur == nil {
                    if n >= 0 && i >= n { return true }
                    let item = s["item"] as? J ?? [:]
                    if snap == nil {
                        var m: [Int: Double] = [:]
                        for x in a.nodesOf(item) { m[x] = a.get(x) }
                        snap = m
                    } else if s["reset"] as? Bool ?? true {
                        for (k, v) in snap! { a.setV(k, v, t) }
                    }
                    cur = a.build(item); i += 1
                }
                if !cur!.update(t) { return false }
                cur = nil
            }
            return n >= 0 && i >= n
        }
    }

    private func build(_ s: J) -> Run {
        switch s["t"] as? String ?? "" {
        case "timing": return Timing(self, s)
        case "spring": return Spring(self, s)
        case "decay": return Decay(self, s)
        case "delay": return DelayRun(Self.d(s["ms"]))
        case "seq": return Seq(self, s)
        case "par": return Par(self, s)
        case "loop": return Loop(self, s)
        default: return Run()
        }
    }

    private func nodesOf(_ s: J) -> Set<Int> {
        if let n = s["node"] as? NSNumber { return [n.intValue] }
        var out = Set<Int>()
        switch s["t"] as? String ?? "" {
        case "seq", "par": for x in s["items"] as? [J] ?? [] { out.formUnion(nodesOf(x)) }
        case "loop": out.formUnion(nodesOf(s["item"] as? J ?? [:]))
        default: break
        }
        return out
    }

    // -- events + frame loop -------------------------------------------------------------------------
    private func emitEnd(_ aid: Int, _ finished: Bool, _ ns: Set<Int>) {
        var vals: J = [:]
        for n in ns { vals[String(n)] = get(n) }
        emit("anim_end", aid, ["finished": finished, "values": vals])
    }

    private func stopTouching(_ ns: Set<Int>, _ finished: Bool) {
        let hit = anims.filter { !$0.nodes.isDisjoint(with: ns) }
        anims.removeAll { a in hit.contains { $0.id == a.id } }
        for h in hit { emitEnd(h.id, finished, h.nodes) }
    }

    private func valueEvents(_ touched: Set<Int>) {
        var ch: J = [:]
        for n in touched where listen.contains(n) {
            let v = get(n)
            if lastSent[n] != v { lastSent[n] = v; ch[String(n)] = v }
        }
        if !ch.isEmpty { emit("anim_value", 0, ch) }
    }

    private final class Target: NSObject {
        weak var owner: Animated?
        @objc func step(_ l: CADisplayLink) { owner?.tick(l.timestamp * 1000) }
    }
    private let target = Target()

    private func start() {
        if link != nil { return }
        target.owner = self
        let l = CADisplayLink(target: target, selector: #selector(Target.step(_:)))
        if #available(iOS 15.0, *) { l.preferredFrameRateRange = CAFrameRateRange(minimum: 60, maximum: 120, preferred: 120) }
        l.add(to: .main, forMode: .common)
        link = l
    }

    private func stop() { link?.invalidate(); link = nil }

    func tick(_ now: Double) {
        var touched = Set<Int>()
        var ended: [Int] = []
        for a in anims {
            touched.formUnion(a.nodes)
            if a.run.update(now) { ended.append(a.id) }
        }
        // no implicit CALayer animation for per-frame writes
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        onFrame(touched)
        CATransaction.commit()
        valueEvents(touched)
        for aid in ended {
            if let k = anims.firstIndex(where: { $0.id == aid }) {
                let r = anims.remove(at: k)
                emitEnd(aid, true, r.nodes)
            }
        }
        if anims.isEmpty { stop() }
    }

    func clear() { anims.removeAll(); stop() }
}
