package dev.pyxpo.runtime

import android.view.Choreographer
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Native animation driver. Kotlin port of pyxpo/animated/engine.py (the reference); numbers are pinned by
 * tests/data/anim_golden.json. One Choreographer callback evaluates every running animation per frame on the UI
 * thread and hands the changed value ids to [onFrame], which writes view properties directly. No Python per frame.
 */
class Animated(
    private val emit: (event: String, id: Int, payload: JSONObject) -> Unit,
    private val onFrame: (touched: Set<Int>) -> Unit,
) {
    // -- easing ------------------------------------------------------------------------------------
    private fun bezier(x1: Double, y1: Double, x2: Double, y2: Double): (Double) -> Double {
        fun coord(a: Double, b: Double, t: Double): Double { val u = 1 - t; return 3 * u * u * t * a + 3 * u * t * t * b + t * t * t }
        return f@{ x ->
            if (x <= 0) return@f 0.0
            if (x >= 1) return@f 1.0
            var lo = 0.0; var hi = 1.0; var t = x
            for (i in 0 until 40) {
                val cx = coord(x1, x2, t)
                if (abs(cx - x) < 1e-7) break
                if (cx < x) lo = t else hi = t
                t = (lo + hi) / 2
            }
            coord(y1, y2, t)
        }
    }

    private fun bounce(t0: Double): Double {
        var t = t0
        if (t < 1 / 2.75) return 7.5625 * t * t
        if (t < 2 / 2.75) { t -= 1.5 / 2.75; return 7.5625 * t * t + 0.75 }
        if (t < 2.5 / 2.75) { t -= 2.25 / 2.75; return 7.5625 * t * t + 0.9375 }
        t -= 2.625 / 2.75
        return 7.5625 * t * t + 0.984375
    }

    fun easing(spec: JSONObject?): (Double) -> Double {
        if (spec == null) return easing(JSONObject("""{"e":"in_out","f":{"e":"quad"}}"""))
        return when (val e = spec.getString("e")) {
            "linear" -> { t -> t }
            "ease" -> bezier(0.42, 0.0, 1.0, 1.0)
            "quad" -> { t -> t * t }
            "cubic" -> { t -> t * t * t }
            "poly" -> { val n = spec.optDouble("n", 4.0); { t -> t.pow(n) } }
            "sin" -> { t -> 1 - cos(t * Math.PI / 2) }
            "circle" -> { t -> 1 - sqrt(max(0.0, 1 - t * t)) }
            "exp" -> { t -> 2.0.pow(10 * (t - 1)) }
            "elastic" -> { val p = spec.optDouble("b", 1.0) * Math.PI; { t -> 1 - cos(t * Math.PI / 2).pow(3) * cos(t * p) } }
            "back" -> { val s = spec.optDouble("s", 1.70158); { t -> t * t * ((s + 1) * t - s) } }
            "bounce" -> { t -> bounce(t) }
            "bezier" -> { val p = spec.getJSONArray("p"); bezier(p.getDouble(0), p.getDouble(1), p.getDouble(2), p.getDouble(3)) }
            "in" -> easing(spec.getJSONObject("f"))
            "out" -> { val f = easing(spec.getJSONObject("f")); { t -> 1 - f(1 - t) } }
            "in_out" -> { val f = easing(spec.getJSONObject("f")); { t -> if (t < 0.5) f(2 * t) / 2 else 1 - f(2 * (1 - t)) / 2 } }
            else -> throw IllegalArgumentException("unknown easing $e")
        }
    }

    // -- node graph --------------------------------------------------------------------------------
    private sealed class N
    private object VNode : N()
    private class INode(val src: Int, val inp: DoubleArray, val out: DoubleArray, val left: String, val right: String,
                        val color: Boolean, val ease: ((Double) -> Double)?) : N()
    private class BNode(val add: Boolean, val a: Int, val b: Int) : N()

    private val nodes = HashMap<Int, N>()
    private val values = HashMap<Int, Double>()
    private val vel = HashMap<Int, Double>()
    private val prev = HashMap<Int, DoubleArray>()          // t, v
    private val listen = HashSet<Int>()
    private val lastSent = HashMap<Int, Double>()
    private class Running(val run: Run, val nodes: Set<Int>)
    private val anims = LinkedHashMap<Int, Running>()
    private val choreographer: Choreographer by lazy { Choreographer.getInstance() }
    private var scheduled = false

    private fun dbl(a: JSONArray) = DoubleArray(a.length()) { a.getDouble(it) }

    fun anode(id: Int, o: JSONObject) {
        when (o.getString("t")) {
            "value" -> { nodes[id] = VNode; values[id] = o.optDouble("v", 0.0) }
            "interp" -> {
                val ex = o.getJSONArray("ex")
                nodes[id] = INode(o.getInt("src"), dbl(o.getJSONArray("in")), dbl(o.getJSONArray("out")), ex.getString(0),
                    ex.getString(1), o.optBoolean("color"), o.optJSONObject("easing")?.let { easing(it) })
            }
            "add", "mul" -> nodes[id] = BNode(o.getString("t") == "add", o.getInt("a"), o.getInt("b"))
        }
    }

    fun anodeDel(id: Int) {
        stopTouching(setOf(id), false)
        nodes.remove(id); values.remove(id); vel.remove(id); prev.remove(id); lastSent.remove(id); listen.remove(id)
    }

    fun alisten(id: Int, on: Boolean) {
        if (on) { listen.add(id); lastSent[id] = values[id] ?: 0.0 } else listen.remove(id)
    }

    fun astop(aid: Int) { anims.remove(aid)?.let { emitEnd(aid, false, it.nodes) } }

    fun aset(vals: JSONObject) {
        val m = HashMap<Int, Double>()
        val it = vals.keys()
        while (it.hasNext()) { val k = it.next(); m[k.toInt()] = vals.getDouble(k) }
        aset(m)
    }

    /** Same as the JSON form, without building a JSONObject (scroll-driven values, every scroll event). */
    fun aset(vals: HashMap<Int, Double>) {
        val ids = vals.keys
        stopTouching(ids, false)
        for ((id, v) in vals) { values[id] = v; vel[id] = 0.0; prev.remove(id) }
        valueEvents(ids)
        onFrame(ids)
    }

    fun animate(aid: Int, spec: JSONObject) {
        val ns = nodesOf(spec)
        stopTouching(ns, false)
        anims[aid] = Running(build(spec), ns)
        schedule()
    }

    fun resolve(id: Int): Double = when (val n = nodes[id]) {
        null -> 0.0
        VNode -> values[id] ?: 0.0
        is INode -> interpolate(resolve(n.src), n)
        is BNode -> if (n.add) resolve(n.a) + resolve(n.b) else resolve(n.a) * resolve(n.b)
    }

    /** Value-node ids a node depends on (itself if it is a value). */
    fun deps(id: Int, out: MutableSet<Int> = HashSet()): MutableSet<Int> {
        when (val n = nodes[id]) {
            VNode -> out.add(id)
            is INode -> deps(n.src, out)
            is BNode -> { deps(n.a, out); deps(n.b, out) }
            null -> {}
        }
        return out
    }

    fun has(id: Int) = nodes.containsKey(id)

    private fun lerpColor(a: Long, b: Long, f: Double): Long {
        var out = 0L
        for (shift in intArrayOf(24, 16, 8, 0)) {
            val ca = ((a shr shift) and 255).toDouble(); val cb = ((b shr shift) and 255).toDouble()
            val v = Math.rint(ca + (cb - ca) * f).toLong().coerceIn(0, 255)
            out = out or (v shl shift)
        }
        return out
    }

    private fun interpolate(x: Double, n: INode): Double {
        val inp = n.inp; val out = n.out; val len = inp.size
        var i: Int
        if (x < inp[0]) {
            if (n.left == "clamp") return out[0]
            if (n.left == "identity") return x
            i = 0
        } else if (x > inp[len - 1]) {
            if (n.right == "clamp") return out[len - 1]
            if (n.right == "identity") return x
            i = len - 2
        } else {
            i = 0
            while (i < len - 2 && x > inp[i + 1]) i++
        }
        val a = inp[i]; val b = inp[i + 1]
        var f = if (b == a) 0.0 else (x - a) / (b - a)
        n.ease?.let { if (f in 0.0..1.0) f = it(f) }
        if (n.color) return lerpColor(out[i].toLong(), out[i + 1].toLong(), f.coerceIn(0.0, 1.0)).toDouble()
        return out[i] + (out[i + 1] - out[i]) * f
    }

    /** Displacement and velocity (per second) of a damped spring dt seconds after release. */
    private fun springAt(dt: Double, x0: Double, v0: Double, k: Double, c: Double, m: Double): DoubleArray {
        val w0 = sqrt(k / m)
        val z = c / (2 * sqrt(k * m))
        if (abs(z - 1) < 1e-9) {
            val e = exp(-w0 * dt); val b = v0 + w0 * x0
            return doubleArrayOf(e * (x0 + b * dt), e * (v0 - w0 * b * dt))
        }
        if (z < 1) {
            val wd = w0 * sqrt(1 - z * z); val e = exp(-z * w0 * dt); val b = (v0 + z * w0 * x0) / wd
            val cs = cos(wd * dt); val sn = sin(wd * dt)
            return doubleArrayOf(e * (x0 * cs + b * sn), e * ((b * wd - z * w0 * x0) * cs - (x0 * wd + z * w0 * b) * sn))
        }
        val s = w0 * sqrt(z * z - 1)
        val r1 = -z * w0 + s; val r2 = -z * w0 - s
        val c2 = (v0 - r1 * x0) / (r2 - r1); val c1 = x0 - c2
        val e1 = exp(r1 * dt); val e2 = exp(r2 * dt)
        return doubleArrayOf(c1 * e1 + c2 * e2, c1 * r1 * e1 + c2 * r2 * e2)
    }

    // -- running animations ------------------------------------------------------------------------
    private fun get(n: Int) = values[n] ?: 0.0
    private fun setV(n: Int, v: Double, t: Double) {
        val p = prev[n]
        if (p != null && t > p[0]) vel[n] = (v - p[1]) / ((t - p[0]) / 1000.0)
        if (p != null) { p[0] = t; p[1] = v } else prev[n] = doubleArrayOf(t, v)
        values[n] = v
    }

    private interface Run { fun update(t: Double): Boolean }

    private inner class Timing(val s: JSONObject) : Run {
        val node = s.getInt("node"); val ease = easing(s.optJSONObject("easing"))
        val ms = s.getDouble("ms"); val to = s.getDouble("to")
        var t0 = Double.NaN; var a = 0.0
        override fun update(t: Double): Boolean {
            if (t0.isNaN()) { t0 = t; a = get(node); prev[node] = doubleArrayOf(t, a) }
            val p = if (ms <= 0) 1.0 else min(1.0, (t - t0) / ms)
            setV(node, if (p >= 1) to else a + (to - a) * ease(p), t)
            return p >= 1
        }
    }

    private inner class Spring(val s: JSONObject) : Run {
        val node = s.getInt("node")
        var t0 = Double.NaN; var x0 = 0.0; var v0 = 0.0
        override fun update(t: Double): Boolean {
            val to = s.getDouble("to")
            if (t0.isNaN()) {
                t0 = t; val a = get(node); x0 = a - to
                v0 = if (s.isNull("v0") || !s.has("v0")) (vel[node] ?: 0.0) else s.getDouble("v0")
                prev[node] = doubleArrayOf(t, a)
            }
            val r = springAt((t - t0) / 1000.0, x0, v0, s.getDouble("k"), s.getDouble("c"), s.getDouble("m"))
            val x = r[0]; val v = r[1]
            var done = abs(x) <= s.optDouble("rest_d", 0.001) && abs(v) <= s.optDouble("rest_v", 0.001)
            if (s.optBoolean("clamp") && t > t0 && x0 != 0.0 && x * x0 <= 0) done = true
            if (x0 == 0.0 && v0 == 0.0) done = true
            setV(node, if (done) to else to + x, t)
            if (done) vel[node] = 0.0
            return done
        }
    }

    private inner class Decay(val s: JSONObject) : Run {
        val node = s.getInt("node")
        var t0 = Double.NaN; var a = 0.0; var v0 = 0.0
        override fun update(t: Double): Boolean {
            val d = s.optDouble("decel", 0.998)
            if (t0.isNaN()) {
                t0 = t; a = get(node)
                v0 = if (s.isNull("v0") || !s.has("v0")) (vel[node] ?: 0.0) / 1000.0 else s.getDouble("v0")
                prev[node] = doubleArrayOf(t, a)
            }
            val k = 1 - d; val dt = t - t0
            setV(node, a + v0 / k * (1 - exp(-k * dt)), t)
            val done = abs(v0 * exp(-k * dt)) * 16.67 < 0.1
            if (done) vel[node] = 0.0
            return done
        }
    }

    private inner class DelayRun(val ms: Double) : Run {
        var t0 = Double.NaN
        override fun update(t: Double): Boolean { if (t0.isNaN()) t0 = t; return t - t0 >= ms }
    }

    private inner class Seq(s: JSONObject) : Run {
        val items = (0 until s.getJSONArray("items").length()).map { build(s.getJSONArray("items").getJSONObject(it)) }
        var i = 0
        override fun update(t: Double): Boolean {
            while (i < items.size) { if (!items[i].update(t)) return false; i++ }
            return true
        }
    }

    private inner class Par(s: JSONObject) : Run {
        val items = (0 until s.getJSONArray("items").length()).map { build(s.getJSONArray("items").getJSONObject(it)) }
        val done = BooleanArray(items.size)
        override fun update(t: Double): Boolean {
            for (k in items.indices) if (!done[k]) done[k] = items[k].update(t)
            return done.all { it }
        }
    }

    private inner class Loop(val s: JSONObject) : Run {
        val n = s.optInt("n", -1); var i = 0; var cur: Run? = null; var snap: HashMap<Int, Double>? = null
        override fun update(t: Double): Boolean {
            for (pass in 0 until 2) {
                if (cur == null) {
                    if (n >= 0 && i >= n) return true
                    val item = s.getJSONObject("item")
                    if (snap == null) snap = HashMap<Int, Double>().also { m -> for (x in nodesOf(item)) m[x] = get(x) }
                    else if (s.optBoolean("reset", true)) for ((k, v) in snap!!) setV(k, v, t)
                    cur = build(item); i++
                }
                if (!cur!!.update(t)) return false
                cur = null
            }
            return n >= 0 && i >= n
        }
    }

    private fun build(s: JSONObject): Run = when (val t = s.getString("t")) {
        "timing" -> Timing(s); "spring" -> Spring(s); "decay" -> Decay(s)
        "delay" -> DelayRun(s.getDouble("ms")); "seq" -> Seq(s); "par" -> Par(s); "loop" -> Loop(s)
        else -> throw IllegalArgumentException("unknown animation $t")
    }

    private fun nodesOf(s: JSONObject): Set<Int> {
        if (s.has("node")) return setOf(s.getInt("node"))
        val out = HashSet<Int>()
        when (s.getString("t")) {
            "seq", "par" -> { val a = s.getJSONArray("items"); for (i in 0 until a.length()) out.addAll(nodesOf(a.getJSONObject(i))) }
            "loop" -> out.addAll(nodesOf(s.getJSONObject("item")))
        }
        return out
    }

    // -- events + frame loop -----------------------------------------------------------------------
    private fun emitEnd(aid: Int, finished: Boolean, ns: Set<Int>) {
        val vals = JSONObject()
        for (n in ns) vals.put(n.toString(), get(n))
        emit("anim_end", aid, JSONObject().put("finished", finished).put("values", vals))
    }

    private fun stopTouching(ns: Set<Int>, finished: Boolean) {
        if (anims.isEmpty()) return  // the common case on every aset (scroll events): no filter copy
        val hit = anims.filter { (_, r) -> r.nodes.any { it in ns } }
        for ((aid, r) in hit) { anims.remove(aid); emitEnd(aid, finished, r.nodes) }
    }

    private fun valueEvents(touched: Set<Int>) {
        val ch = JSONObject()
        for (n in touched) if (n in listen) {
            val v = get(n)
            if (lastSent[n] != v) { lastSent[n] = v; ch.put(n.toString(), v) }
        }
        if (ch.length() > 0) emit("anim_value", 0, ch)
    }

    private val frameCb = Choreographer.FrameCallback { nanos ->
        scheduled = false
        tick(nanos / 1_000_000.0)
        if (anims.isNotEmpty()) schedule()
    }

    private fun schedule() {
        if (!scheduled) { scheduled = true; choreographer.postFrameCallback(frameCb) }
    }

    fun tick(now: Double) {
        val touched = HashSet<Int>()
        val ended = ArrayList<Int>()
        for ((aid, r) in anims) {
            touched.addAll(r.nodes)
            if (r.run.update(now)) ended.add(aid)
        }
        onFrame(touched)          // views first, so Python sees the final frame already drawn
        valueEvents(touched)
        for (aid in ended) anims.remove(aid)?.let { emitEnd(aid, true, it.nodes) }
    }

    fun clear() { anims.clear(); choreographer.removeFrameCallback(frameCb); scheduled = false }
}
