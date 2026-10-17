package dev.pyxpo.modules.whiteboard

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PorterDuff
import android.graphics.PorterDuffXfermode
import android.graphics.RectF
import android.view.MotionEvent
import android.view.View
import dev.pyxpo.moduleapi.PxNativeView
import org.json.JSONObject
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt
import kotlin.math.sin

private fun u32(c: Int): Long = c.toLong() and 0xFFFFFFFFL

/** One stroke, shape or fill, in dp from the view's top left. A fill keeps its point in x0, y0. */
class Element(val type: String, val color: Int) {
    var tool = "pen"
    var shape = ""
    var width = 0f
    var fill = 0
    val points: MutableList<Float> = mutableListOf()
    var x0 = 0f; var y0 = 0f; var x1 = 0f; var y1 = 0f

    fun json(): Map<String, Any> = when (type) {
        "stroke" -> mapOf("type" to "stroke", "tool" to tool, "color" to u32(color), "width" to width.toDouble(),
                          "points" to points.map { it.toDouble() })
        "shape" -> mapOf("type" to "shape", "shape" to shape, "color" to u32(color), "width" to width.toDouble(),
                         "fill" to u32(fill), "x0" to x0.toDouble(), "y0" to y0.toDouble(), "x1" to x1.toDouble(),
                         "y1" to y1.toDouble())
        else -> mapOf("type" to "fill", "x" to x0.toDouble(), "y" to y0.toDouble(), "color" to u32(color))
    }

    /** Draws any element; false when a fill changed nothing. A fill needs `bitmap` (the committed ink). */
    fun render(c: Canvas, k: Float, tol: Int, bitmap: Bitmap?): Boolean {
        if (type == "fill") return bitmap != null && flood(bitmap, this, k, tol)
        draw(c, k)
        return true
    }

    /** Draws a stroke or a shape. */
    fun draw(c: Canvas, k: Float) {
        val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            strokeCap = Paint.Cap.ROUND
            strokeJoin = Paint.Join.ROUND
        }
        if (type == "shape") {
            val (path, closed) = path(k)
            if (closed && fill ushr 24 != 0) {
                paint.style = Paint.Style.FILL
                paint.color = fill
                c.drawPath(path, paint)
            }
            if (width > 0) {
                paint.style = Paint.Style.STROKE
                paint.color = color
                paint.strokeWidth = width * k
                c.drawPath(path, paint)
            }
            return
        }
        if (type != "stroke") return
        // Same curve on every platform: quadratic segments through the midpoints, a dot for a single point.
        paint.color = color
        if (tool == "eraser") paint.xfermode = PorterDuffXfermode(PorterDuff.Mode.CLEAR)
        val p = points
        val n = p.size / 2
        if (n == 1) {
            paint.style = Paint.Style.FILL
            c.drawCircle(p[0] * k, p[1] * k, width * k / 2, paint)
            return
        }
        if (n < 2) return
        paint.style = Paint.Style.STROKE
        paint.strokeWidth = width * k
        val path = Path()
        path.moveTo(p[0] * k, p[1] * k)
        for (i in 1 until n - 1) {
            path.quadTo(p[2 * i] * k, p[2 * i + 1] * k, (p[2 * i] + p[2 * i + 2]) / 2 * k, (p[2 * i + 1] + p[2 * i + 3]) / 2 * k)
        }
        path.lineTo(p[2 * n - 2] * k, p[2 * n - 1] * k)
        c.drawPath(path, paint)
    }

    /** Arrow head line end: 28 degrees off the shaft, max(12, 3.5 x width) long, at most half the shaft. */
    private fun arrowHead(side: Float): Pair<Float, Float> {
        val dx = x1 - x0
        val dy = y1 - y0
        val n = max(hypot(dx, dy), 1e-9f)
        val size = min(max(12f, width * 3.5f), n * 0.5f)
        val a = atan2(dy, dx) + PI.toFloat() + side * 28f * PI.toFloat() / 180f
        return Pair(x1 + size * cos(a), y1 + size * sin(a))
    }

    /** The shape's path and whether it is closed (can be filled). */
    private fun path(k: Float): Pair<Path, Boolean> {
        val lx = min(x0, x1); val ly = min(y0, y1); val hx = max(x0, x1); val hy = max(y0, y1)
        val cx = (lx + hx) / 2; val cy = (ly + hy) / 2; val rx = (hx - lx) / 2; val ry = (hy - ly) / 2
        val p = Path()
        when (shape) {
            "line", "arrow" -> {
                p.moveTo(x0 * k, y0 * k)
                p.lineTo(x1 * k, y1 * k)
                if (shape == "arrow") {
                    for (side in floatArrayOf(-1f, 1f)) {
                        val (hxp, hyp) = arrowHead(side)
                        p.moveTo(x1 * k, y1 * k)
                        p.lineTo(hxp * k, hyp * k)
                    }
                }
                return Pair(p, false)
            }
            "rect" -> p.addRect(lx * k, ly * k, hx * k, hy * k, Path.Direction.CW)
            "ellipse" -> p.addOval(RectF(lx * k, ly * k, hx * k, hy * k), Path.Direction.CW)
            "triangle" -> {
                p.moveTo(cx * k, ly * k)
                p.lineTo(hx * k, hy * k)
                p.lineTo(lx * k, hy * k)
                p.close()
            }
            else -> {  // star
                for (j in 0 until 10) {
                    val a = -PI.toFloat() / 2 + PI.toFloat() * j / 5
                    val r = if (j % 2 == 0) 1f else 0.45f
                    val x = (cx + rx * r * cos(a)) * k
                    val y = (cy + ry * r * sin(a)) * k
                    if (j == 0) p.moveTo(x, y) else p.lineTo(x, y)
                }
                p.close()
            }
        }
        return Pair(p, true)
    }

    companion object {
        val SHAPES = setOf("line", "arrow", "rect", "ellipse", "triangle", "star")

        fun from(o: JSONObject?): Element? {
            o ?: return null
            val type = o.optString("type", "stroke")
            val e = Element(type, o.optLong("color", 0xFF000000L).toInt())
            when (type) {
                "stroke" -> {
                    val pts = o.optJSONArray("points") ?: return null
                    if (pts.length() == 0 || pts.length() % 2 != 0) return null
                    e.tool = o.optString("tool", "pen")
                    e.width = o.optDouble("width", 4.0).toFloat()
                    for (i in 0 until pts.length()) e.points.add(pts.getDouble(i).toFloat())
                }
                "shape" -> {
                    val s = o.optString("shape")
                    if (s !in SHAPES) return null
                    for (key in listOf("x0", "y0", "x1", "y1")) if (!o.has(key)) return null
                    e.shape = s
                    e.width = o.optDouble("width", 4.0).toFloat()
                    e.fill = o.optLong("fill", 0L).toInt()
                    e.x0 = o.getDouble("x0").toFloat(); e.y0 = o.getDouble("y0").toFloat()
                    e.x1 = o.getDouble("x1").toFloat(); e.y1 = o.getDouble("y1").toFloat()
                }
                "fill" -> {
                    if (!o.has("x") || !o.has("y")) return null
                    e.x0 = o.getDouble("x").toFloat(); e.y0 = o.getDouble("y").toFloat()
                }
                else -> return null
            }
            return e
        }

        /** Premultiplied [r, g, b, a] of an Android (unpremultiplied) ARGB pixel. */
        private fun pre(c: Int): IntArray {
            val a = c ushr 24
            return intArrayOf(((c shr 16) and 255) * a / 255, ((c shr 8) and 255) * a / 255, (c and 255) * a / 255, a)
        }

        /**
         * Bucket fill: the 4-connected region within `tol` of the tapped pixel (compared premultiplied, like web
         * and iOS) gets the fill color, and the 1px ring around it gets the fill under its own color so the fill
         * meets anti-aliased lines without a gap. False when nothing would change.
         */
        fun flood(b: Bitmap, e: Element, k: Float, tol: Int): Boolean {
            val w = b.width
            val h = b.height
            val sx = floor(e.x0 * k).toInt()
            val sy = floor(e.y0 * k).toInt()
            if (sx < 0 || sy < 0 || sx >= w || sy >= h) return false
            val px = IntArray(w * h)
            b.getPixels(px, 0, w, 0, 0, w, h)
            val f = pre(e.color)
            val s = pre(px[sy * w + sx])
            if ((0 until 4).all { abs(f[it] - s[it]) <= 2 }) return false
            val mask = ByteArray(w * h)  // 1 region, 2 ring
            fun match(x: Int, y: Int): Boolean {
                val i = y * w + x
                if (mask[i].toInt() == 1) return false
                val c = px[i]
                val a = c ushr 24
                return abs(a - s[3]) <= tol && abs(((c shr 16) and 255) * a / 255 - s[0]) <= tol &&
                    abs(((c shr 8) and 255) * a / 255 - s[1]) <= tol && abs((c and 255) * a / 255 - s[2]) <= tol
            }
            val stack = ArrayList<Int>()
            stack.add(sx); stack.add(sy)
            while (stack.isNotEmpty()) {
                val y = stack.removeAt(stack.size - 1)
                var x = stack.removeAt(stack.size - 1)
                if (!match(x, y)) continue
                while (x > 0 && match(x - 1, y)) x--
                var up = false
                var down = false
                while (x < w && match(x, y)) {
                    mask[y * w + x] = 1
                    if (y > 0) {
                        val m = match(x, y - 1)
                        if (m && !up) { stack.add(x); stack.add(y - 1) }
                        up = m
                    }
                    if (y < h - 1) {
                        val m = match(x, y + 1)
                        if (m && !down) { stack.add(x); stack.add(y + 1) }
                        down = m
                    }
                    x++
                }
            }
            for (y in 0 until h) for (x in 0 until w) {
                val i = y * w + x
                if (mask[i].toInt() != 0) continue
                if ((x > 0 && mask[i - 1].toInt() == 1) || (x < w - 1 && mask[i + 1].toInt() == 1) ||
                    (y > 0 && mask[i - w].toInt() == 1) || (y < h - 1 && mask[i + w].toInt() == 1)) mask[i] = 2
            }
            for (i in 0 until w * h) {
                when (mask[i].toInt()) {
                    1 -> px[i] = e.color
                    2 -> {  // existing over fill, then back to unpremultiplied
                        val q = pre(px[i])
                        val inv = 255 - q[3]
                        val a = min(255, q[3] + f[3] * inv / 255)
                        if (a == 0) continue
                        val r = min(255, q[0] + f[0] * inv / 255) * 255 / a
                        val g = min(255, q[1] + f[1] * inv / 255) * 255 / a
                        val bl = min(255, q[2] + f[2] * inv / 255) * 255 / a
                        px[i] = (a shl 24) or (min(255, r) shl 16) or (min(255, g) shl 8) or min(255, bl)
                    }
                }
            }
            b.setPixels(px, 0, w, 0, 0, w, h)
            return true
        }
    }
}

class WhiteboardView(context: Context, emit: (String, Any?) -> Unit) : PxNativeView {
    val board = BoardView(context, emit)
    override val view: View get() = board

    override fun update(props: JSONObject, removed: Set<String>) {
        if (props.has("tool")) board.tool = props.getString("tool")
        if (props.has("color")) board.color = props.getLong("color").toInt()
        if (props.has("width")) board.lineWidth = props.getDouble("width").toFloat()
        if (props.has("fill_color")) board.fillColor = props.getLong("fill_color").toInt()
        if (props.has("enabled")) board.drawEnabled = props.getBoolean("enabled")
        if (props.has("fill_tolerance")) board.setTolerance(props.getInt("fill_tolerance"))
        if (props.has("background_color")) {
            board.bgColor = props.getLong("background_color").toInt()
            board.setBackgroundColor(board.bgColor)
        }
    }
}

@SuppressLint("ViewConstructor")
class BoardView(context: Context, private val emit: (String, Any?) -> Unit) : View(context) {
    private sealed class Op {
        class Add(val element: Element) : Op()
        class Clear(val old: List<Element>) : Op()
    }

    var elements: MutableList<Element> = mutableListOf()
        private set
    private val history = ArrayList<Op>()
    private val future = ArrayList<Op>()
    private var live: Element? = null
    private var pointer = -1
    private var done: Bitmap? = null
    private val density = resources.displayMetrics.density
    var tool = "pen"
    var color = 0xFF000000.toInt()
    var lineWidth = 4f
    var fillColor = 0
    var drawEnabled = true
    var bgColor = -1  // white
    var tolerance = 32
        private set

    init {
        setBackgroundColor(bgColor)
    }

    fun setTolerance(t: Int) {
        if (t == tolerance) return
        tolerance = t
        if (elements.any { it.type == "fill" }) rebuild()
    }

    private fun state() {
        emit("change", mapOf("element_count" to elements.size, "can_undo" to history.isNotEmpty(), "can_redo" to future.isNotEmpty()))
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        rebuild()
    }

    private fun rebuild() {
        done?.recycle()
        done = if (width > 0 && height > 0) Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888).also { b ->
            val c = Canvas(b)
            for (e in elements) e.render(c, density, tolerance, b)
        } else null
        invalidate()
    }

    private fun commit(e: Element): Boolean {
        val b = done ?: return false
        if (!e.render(Canvas(b), density, tolerance, b)) return false
        elements.add(e)
        history.add(Op.Add(e))
        future.clear()
        return true
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        // A layer so the eraser clears ink only, not the background drawn under it.
        val save = canvas.saveLayer(0f, 0f, width.toFloat(), height.toFloat(), null)
        done?.let { canvas.drawBitmap(it, 0f, 0f, null) }
        live?.draw(canvas, density)
        canvas.restoreToCount(save)
    }

    private fun dp(v: Float): Float = (v / density * 10).roundToInt() / 10f

    private fun add(x: Float, y: Float) {
        val e = live ?: return
        val px = dp(x)
        val py = dp(y)
        if (e.type == "shape") {
            e.x1 = px; e.y1 = py
            return
        }
        val n = e.points.size
        if (n > 0 && abs(e.points[n - 2] - px) < 0.5f && abs(e.points[n - 1] - py) < 0.5f) return
        e.points.add(px)
        e.points.add(py)
    }

    @SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(e: MotionEvent): Boolean {
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                if (!drawEnabled) return false
                emit("draw_start", mapOf("tool" to tool))
                if (tool == "fill") {
                    val f = Element("fill", color)
                    f.x0 = dp(e.x); f.y0 = dp(e.y)
                    commit(f)
                    invalidate()
                    state()
                    return true
                }
                pointer = e.getPointerId(0)
                parent?.requestDisallowInterceptTouchEvent(true)
                live = if (tool in Element.SHAPES) Element("shape", color).apply {
                    shape = tool; width = lineWidth; fill = fillColor
                    x0 = dp(e.x); y0 = dp(e.y); x1 = x0; y1 = y0
                } else Element("stroke", color).apply { this.tool = this@BoardView.tool; width = lineWidth }
                add(e.x, e.y)
                invalidate()
            }
            MotionEvent.ACTION_MOVE -> {
                val i = e.findPointerIndex(pointer)
                if (i < 0 || live == null) return true
                for (hIdx in 0 until e.historySize) add(e.getHistoricalX(i, hIdx), e.getHistoricalY(i, hIdx))
                add(e.getX(i), e.getY(i))
                invalidate()
            }
            MotionEvent.ACTION_POINTER_UP -> {
                if (e.getPointerId(e.actionIndex) == pointer) finish(true)
            }
            MotionEvent.ACTION_UP -> {
                val i = e.findPointerIndex(pointer)
                if (i >= 0 && live != null) add(e.getX(i), e.getY(i))
                finish(true)
            }
            MotionEvent.ACTION_CANCEL -> finish(false)
        }
        return true
    }

    private fun finish(keep: Boolean) {
        if (pointer < 0 && live == null) return
        pointer = -1
        val e = live
        live = null
        if (keep && e != null) {
            val big = e.type != "shape" || abs(e.x1 - e.x0) >= 2 || abs(e.y1 - e.y0) >= 2
            if (big && (e.type == "shape" || e.points.isNotEmpty())) commit(e)
        }
        invalidate()
        state()
    }

    fun undo() {
        val op = history.removeLastOrNull() ?: return
        when (op) {
            is Op.Add -> elements.removeAt(elements.size - 1)
            is Op.Clear -> elements = op.old.toMutableList()
        }
        future.add(op)
        rebuild()
        state()
    }

    fun redo() {
        val op = future.removeLastOrNull() ?: return
        when (op) {
            is Op.Add -> elements.add(op.element)
            is Op.Clear -> elements = mutableListOf()
        }
        history.add(op)
        rebuild()
        state()
    }

    fun clear() {
        if (elements.isEmpty()) return
        history.add(Op.Clear(elements.toList()))
        future.clear()
        elements = mutableListOf()
        rebuild()
        state()
    }

    fun setElements(list: List<Element>) {
        elements = list.toMutableList()
        history.clear()
        future.clear()
        rebuild()
        state()
    }
}
