package dev.pyxpo.modules.keyboard

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.graphics.Typeface
import android.os.Handler
import android.os.Looper
import android.view.MotionEvent
import android.view.View
import kotlin.math.abs

enum class Shift { OFF, ONCE, LOCK }

/** Key colors for one system theme. */
class Palette(val dark: Boolean) {
    val background = if (dark) 0xFF1B1B1F.toInt() else 0xFFE4E6EA.toInt()
    val key = if (dark) 0xFF3B3B40.toInt() else 0xFFFFFFFF.toInt()
    val special = if (dark) 0xFF2A2A2F.toInt() else 0xFFC9CDD3.toInt()
    val pressed = if (dark) 0xFF5C5C63.toInt() else 0xFFAEB3BA.toInt()
    val text = if (dark) 0xFFECECEF.toInt() else 0xFF1F2023.toInt()
    val muted = if (dark) 0xFF9A9AA2.toInt() else 0xFF6B6F76.toInt()
    val accent = if (dark) 0xFF8AB4F8.toInt() else 0xFF1A73E8.toInt()
    val onAccent = if (dark) 0xFF0F1A2E.toInt() else 0xFFFFFFFF.toInt()
}

/**
 * The key grid, drawn on one canvas so a tap never waits for layout or Python. Touch: a key fires on release,
 * or as soon as another finger goes down (fast two-thumb typing). Holding a key with an `alt` types the alt;
 * holding delete repeats it.
 */
@SuppressLint("ViewConstructor")
class KeyboardView(context: Context, private val listener: Listener) : View(context) {
    interface Listener {
        fun onKey(key: Key)
        /** A held key; true when it did something, so the release does not type the key too. */
        fun onHold(key: Key): Boolean
        fun onRepeat(key: Key)
    }

    var rows: List<List<Key>> = emptyList()
        set(value) { field = value; requestLayout(); placed = false; invalidate() }
    var shift = Shift.OFF
        set(value) { field = value; invalidate() }
    /** What the enter key shows: an action word ("Go", "Send", ...) or null for the return arrow. */
    var enterLabel: String? = null
        set(value) { field = value; invalidate() }
    var spaceLabel = ""
        set(value) { field = value; invalidate() }
    var palette = Palette(false)
        set(value) { field = value; invalidate() }

    private val density = resources.displayMetrics.density
    private val rowHeight = 54 * density
    private val gap = 6 * density
    private val pad = 4 * density
    private val radius = 7 * density
    private var placed = false

    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val label = Paint(Paint.ANTI_ALIAS_FLAG).apply { textAlign = Paint.Align.CENTER }
    private val hint = Paint(Paint.ANTI_ALIAS_FLAG).apply { textAlign = Paint.Align.RIGHT; textSize = 10 * density }
    private val rect = RectF()
    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE; strokeWidth = 2 * density; strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND
    }
    private val path = Path()

    private val handler = Handler(Looper.getMainLooper())
    /** pointer id -> the key it holds */
    private val down = HashMap<Int, Key>()
    private val held = HashSet<Key>()          // keys whose hold already fired
    private var repeating: Runnable? = null
    private var holding: Runnable? = null

    override fun onMeasure(widthSpec: Int, heightSpec: Int) {
        val w = MeasureSpec.getSize(widthSpec)
        setMeasuredDimension(w, (rows.size * rowHeight + 2 * pad).toInt())
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        placed = false
    }

    private fun place() {
        val inner = width - 2 * pad
        rows.forEachIndexed { r, row ->
            val units = row.sumOf { it.width.toDouble() }.toFloat()
            // rows narrower than the widest letter row keep letter-sized keys, centered
            val unit = inner / maxOf(units, 10f)
            var x = pad + (inner - units * unit) / 2
            for (k in row) {
                k.x = x; k.y = pad + r * rowHeight; k.w = k.width * unit; k.h = rowHeight
                x += k.w
            }
        }
        placed = true
    }

    override fun onDraw(canvas: Canvas) {
        if (!placed) place()
        canvas.drawColor(palette.background)
        for (row in rows) for (k in row) if (k.code != Codes.SPACER) drawKey(canvas, k)
    }

    private fun drawKey(canvas: Canvas, k: Key) {
        val enter = k.code == Codes.ENTER
        val pressed = down.values.any { it === k }
        fill.color = when {
            pressed -> palette.pressed
            enter -> palette.accent
            k.special -> palette.special
            else -> palette.key
        }
        rect.set(k.x + gap / 2, k.y + gap / 2 + density, k.x + k.w - gap / 2, k.y + k.h - gap / 2)
        canvas.drawRoundRect(rect, radius, radius, fill)

        val text = face(k)
        val big = k.code == 0 && text.length == 1
        label.color = if (enter && !pressed) palette.onAccent else if (k.code == Codes.SPACE) palette.muted else palette.text
        if (k.code == Codes.ENTER && enterLabel == null) return drawReturn(canvas, label.color)
        label.textSize = (if (big) 22 else if (text.length > 3) 13 else 16) * density
        label.typeface = if (k.code == Codes.SHIFT && shift == Shift.LOCK) Typeface.DEFAULT_BOLD else Typeface.DEFAULT
        val cy = rect.centerY() - (label.descent() + label.ascent()) / 2
        canvas.drawText(text, rect.centerX(), cy, label)
        if (k.code == Codes.SHIFT && shift == Shift.LOCK) {
            fill.color = palette.text
            canvas.drawRect(rect.centerX() - 7 * density, rect.bottom - 9 * density, rect.centerX() + 7 * density,
                            rect.bottom - 7 * density, fill)
        }
        val alt = k.alt
        if (alt != null && alt.isNotBlank()) {
            hint.color = palette.muted
            canvas.drawText(alt, rect.right - 4 * density, rect.top + 12 * density, hint)
        }
    }

    /** The return arrow, drawn: the font's "↵" is tiny at any size. */
    private fun drawReturn(canvas: Canvas, color: Int) {
        val u = 4 * density
        val cx = rect.centerX(); val cy = rect.centerY()
        stroke.color = color
        path.reset()
        path.moveTo(cx + 2 * u, cy - 2 * u); path.lineTo(cx + 2 * u, cy + u); path.lineTo(cx - 2.5f * u, cy + u)
        path.moveTo(cx - 1.2f * u, cy - 0.3f * u); path.lineTo(cx - 2.5f * u, cy + u); path.lineTo(cx - 1.2f * u, cy + 2.3f * u)
        canvas.drawPath(path, stroke)
    }

    private fun face(k: Key): String = when (k.code) {
        Codes.SHIFT -> if (shift == Shift.OFF) "⇧" else "⬆"
        Codes.DELETE -> "⌫"
        Codes.ENTER -> enterLabel ?: "↵"
        Codes.EMOJI -> "☺"
        Codes.GLOBE -> "🌐"
        Codes.SPACE -> spaceLabel
        0 -> if (shift != Shift.OFF && k.label.length == 1) k.label.uppercase() else k.label
        else -> k.label
    }

    /** The key under (x, y): the row by height, then the nearest key in it, so gaps between keys still type. */
    private fun keyAt(x: Float, y: Float): Key? {
        if (rows.isEmpty()) return null
        if (!placed) place()
        val r = ((y - pad) / rowHeight).toInt().coerceIn(0, rows.size - 1)
        return rows[r].filter { it.code != Codes.SPACER }.minByOrNull { k ->
            if (x >= k.x && x < k.x + k.w) 0f else minOf(abs(x - k.x), abs(x - k.x - k.w))
        }
    }

    @SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(e: MotionEvent): Boolean {
        val i = e.actionIndex
        val id = e.getPointerId(i)
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN, MotionEvent.ACTION_POINTER_DOWN -> {
                // another finger down: the earlier key fires now, as if released
                for ((other, k) in down.entries.toList()) if (other != id) release(other, k, fire = true)
                val k = keyAt(e.getX(i), e.getY(i)) ?: return true
                down[id] = k
                press(k)
            }
            MotionEvent.ACTION_MOVE -> {
                for (p in 0 until e.pointerCount) {
                    val pid = e.getPointerId(p)
                    val k = down[pid] ?: continue
                    if (k.code == Codes.DELETE || held.contains(k)) continue
                    val now = keyAt(e.getX(p), e.getY(p)) ?: continue
                    if (now !== k) { cancelTimers(); down[pid] = now; press(now, timers = false) }
                }
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_POINTER_UP -> down[id]?.let { release(id, it, fire = true) }
            MotionEvent.ACTION_CANCEL -> { cancelTimers(); down.clear(); held.clear(); invalidate() }
        }
        return true
    }

    private fun press(k: Key, timers: Boolean = true) {
        invalidate()
        if (!timers) return
        if (k.code == Codes.DELETE) {
            listener.onKey(k)       // delete acts on press, then repeats while held
            held.add(k)
            val r = object : Runnable {
                override fun run() { listener.onRepeat(k); handler.postDelayed(this, 50) }
            }
            repeating = r
            handler.postDelayed(r, 400)
        } else if (k.alt != null || k.code == Codes.SPACE || k.code == Codes.SHIFT) {
            val r = Runnable { if (listener.onHold(k)) { held.add(k); invalidate() } }
            holding = r
            handler.postDelayed(r, 380)
        }
    }

    private fun release(id: Int, k: Key, fire: Boolean) {
        down.remove(id)
        cancelTimers()
        if (fire && !held.remove(k)) listener.onKey(k)
        held.remove(k)
        invalidate()
    }

    private fun cancelTimers() {
        repeating?.let { handler.removeCallbacks(it) }
        holding?.let { handler.removeCallbacks(it) }
        repeating = null
        holding = null
    }

    override fun onDetachedFromWindow() {
        cancelTimers()
        down.clear()
        held.clear()
        super.onDetachedFromWindow()
    }
}
