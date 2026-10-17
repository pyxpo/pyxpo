package dev.pyxpo.modules.drawingcanvas

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PorterDuff
import android.graphics.PorterDuffXfermode
import android.view.MotionEvent
import android.view.View
import dev.pyxpo.moduleapi.PxNativeView
import org.json.JSONObject
import kotlin.math.abs
import kotlin.math.roundToInt

/** One stroke. `points` is flat [x0, y0, x1, y1, ...] in dp from the view's top left. */
class Stroke(val tool: String, val color: Int, val width: Float, val points: MutableList<Float> = mutableListOf()) {
    fun json(): Map<String, Any> = mapOf("tool" to tool, "color" to (color.toLong() and 0xFFFFFFFFL), "width" to width.toDouble(),
                                         "points" to points.map { it.toDouble() })

    /** Same curve on every platform: quadratic segments through the midpoints, a dot for a single point. */
    fun draw(c: Canvas, k: Float) {
        val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = this@Stroke.color
            if (tool == "eraser") xfermode = PorterDuffXfermode(PorterDuff.Mode.CLEAR)
        }
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
        paint.strokeCap = Paint.Cap.ROUND
        paint.strokeJoin = Paint.Join.ROUND
        val path = Path()
        path.moveTo(p[0] * k, p[1] * k)
        for (i in 1 until n - 1) {
            path.quadTo(p[2 * i] * k, p[2 * i + 1] * k, (p[2 * i] + p[2 * i + 2]) / 2 * k, (p[2 * i + 1] + p[2 * i + 3]) / 2 * k)
        }
        path.lineTo(p[2 * n - 2] * k, p[2 * n - 1] * k)
        c.drawPath(path, paint)
    }

    companion object {
        fun from(o: JSONObject?): Stroke? {
            val pts = o?.optJSONArray("points") ?: return null
            if (pts.length() == 0 || pts.length() % 2 != 0) return null
            return Stroke(o.optString("tool", "pen"), o.optLong("color", 0xFF000000L).toInt(), o.optDouble("width", 4.0).toFloat(),
                          (0 until pts.length()).map { pts.getDouble(it).toFloat() }.toMutableList())
        }
    }
}

class DrawingCanvasView(context: Context, emit: (String, Any?) -> Unit) : PxNativeView {
    val canvas = CanvasView(context, emit)
    override val view: View get() = canvas

    override fun update(props: JSONObject, removed: Set<String>) {
        if (props.has("stroke_color")) canvas.strokeColor = props.getLong("stroke_color").toInt()
        if (props.has("stroke_width")) canvas.strokeWidth = props.getDouble("stroke_width").toFloat()
        if (props.has("tool")) canvas.tool = props.getString("tool")
        if (props.has("enabled")) canvas.drawEnabled = props.getBoolean("enabled")
        if (props.has("background_color")) {
            canvas.bgColor = props.getLong("background_color").toInt()
            canvas.setBackgroundColor(canvas.bgColor)
        }
    }
}

@SuppressLint("ViewConstructor")
class CanvasView(context: Context, private val emit: (String, Any?) -> Unit) : View(context) {
    private sealed class Op {
        class Add(val stroke: Stroke) : Op()
        class Clear(val old: List<Stroke>) : Op()
    }

    var strokes: MutableList<Stroke> = mutableListOf()
        private set
    private val history = ArrayList<Op>()
    private val future = ArrayList<Op>()
    private var live: Stroke? = null
    private var pointer = -1
    private var done: Bitmap? = null
    private val density = resources.displayMetrics.density
    var strokeColor = 0xFF000000.toInt()
    var strokeWidth = 4f
    var tool = "pen"
    var drawEnabled = true
    var bgColor = -1  // white

    init {
        setBackgroundColor(bgColor)
    }

    private fun state() {
        emit("change", mapOf("stroke_count" to strokes.size, "can_undo" to history.isNotEmpty(), "can_redo" to future.isNotEmpty()))
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        rebuild()
    }

    private fun rebuild() {
        done?.recycle()
        done = if (width > 0 && height > 0) Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888).also { b ->
            val c = Canvas(b)
            for (s in strokes) s.draw(c, density)
        } else null
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        // A layer so the eraser clears ink only, not the background drawn under it.
        val save = canvas.saveLayer(0f, 0f, width.toFloat(), height.toFloat(), null)
        done?.let { canvas.drawBitmap(it, 0f, 0f, null) }
        live?.draw(canvas, density)
        canvas.restoreToCount(save)
    }

    private fun add(x: Float, y: Float) {
        val s = live ?: return
        val px = (x / density * 10).roundToInt() / 10f
        val py = (y / density * 10).roundToInt() / 10f
        val n = s.points.size
        if (n > 0 && abs(s.points[n - 2] - px) < 0.5f && abs(s.points[n - 1] - py) < 0.5f) return
        s.points.add(px)
        s.points.add(py)
    }

    @SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(e: MotionEvent): Boolean {
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                if (!drawEnabled) return false
                pointer = e.getPointerId(0)
                parent?.requestDisallowInterceptTouchEvent(true)
                live = Stroke(tool, strokeColor, strokeWidth)
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
        pointer = -1
        val s = live
        live = null
        if (keep && s != null && s.points.isNotEmpty()) {
            strokes.add(s)
            history.add(Op.Add(s))
            future.clear()
            done?.let { s.draw(Canvas(it), density) }
            state()
        }
        invalidate()
    }

    fun undo() {
        val op = history.removeLastOrNull() ?: return
        when (op) {
            is Op.Add -> strokes.removeAt(strokes.size - 1)
            is Op.Clear -> strokes = op.old.toMutableList()
        }
        future.add(op)
        rebuild()
        state()
    }

    fun redo() {
        val op = future.removeLastOrNull() ?: return
        when (op) {
            is Op.Add -> strokes.add(op.stroke)
            is Op.Clear -> strokes = mutableListOf()
        }
        history.add(op)
        rebuild()
        state()
    }

    fun clear() {
        if (strokes.isEmpty()) return
        history.add(Op.Clear(strokes.toList()))
        future.clear()
        strokes = mutableListOf()
        rebuild()
        state()
    }

    fun setStrokes(list: List<Stroke>) {
        strokes = list.toMutableList()
        history.clear()
        future.clear()
        rebuild()
        state()
    }
}
