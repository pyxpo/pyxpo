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

/** Key colors for one system theme, iOS style: black with graphite keys at night, white keys on light grey by day. */
class Palette(val dark: Boolean) {
    val background = if (dark) 0xFF000000.toInt() else 0xFFD1D3D9.toInt()
    val key = if (dark) 0xFF5C5C60.toInt() else 0xFFFFFFFF.toInt()
    val special = if (dark) 0xFF333336.toInt() else 0xFFACB1BA.toInt()
    val pressed = if (dark) 0xFF8E8E93.toInt() else 0xFFC4C8CF.toInt()
    val text = if (dark) 0xFFFFFFFF.toInt() else 0xFF000000.toInt()
    val muted = if (dark) 0xFFAEAEB2.toInt() else 0xFF5F636A.toInt()
    /** Cards and chips on the app panel: darker than a key so white text stays easy on the eye. */
    val card = if (dark) 0xFF1C1C1E.toInt() else 0xFFFFFFFF.toInt()
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
    /** What the enter key shows: an action word ("Go", "Send", ...) or null for "return". */
    var enterLabel: String? = null
        set(value) { field = value; invalidate() }
    var spaceLabel = ""
        set(value) { field = value; invalidate() }
    var palette = Palette(false)
        set(value) { field = value; invalidate() }

    private val density = resources.displayMetrics.density
    // iOS-like proportions: tall keys, narrow gaps between keys, wider ones between rows, round corners
    private val rowHeight = 56 * density
    private val gap = 6 * density
    private val rowGap = 11 * density
    private val pad = 3 * density
    private val radius = 13 * density
    private var placed = false

    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val label = Paint(Paint.ANTI_ALIAS_FLAG).apply { textAlign = Paint.Align.CENTER }
    private val letterFace = Typeface.create("sans-serif", Typeface.NORMAL)
    private val rect = RectF()
    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE; strokeWidth = 2 * density; strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND
    }
    private val path = Path()
    private val iconLine = Icons.line(density)
    private val iconSolid = Icons.solid()

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
        val pressed = down.values.any { it === k }
        // shift on: a light key with a dark arrow, so the uppercase labels still tell what types
        val lit = k.code == Codes.SHIFT && shift != Shift.OFF && !pressed
        // an action word on the enter key (Send, Go, Search) is the one coloured key
        val action = k.code == Codes.ENTER && enterLabel != null && !pressed
        fill.color = when {
            pressed -> palette.pressed
            lit -> palette.text
            action -> palette.accent
            k.special || k.side -> palette.special
            else -> palette.key
        }
        rect.set(k.x + gap / 2, k.y + rowGap / 2, k.x + k.w - gap / 2, k.y + k.h - rowGap / 2)
        canvas.drawRoundRect(rect, radius, radius, fill)

        val ink = if (lit) palette.background else if (action) palette.onAccent else palette.text
        when {
            k.code == Codes.SHIFT -> return drawShift(canvas, ink, shift == Shift.LOCK)
            k.code == Codes.DELETE -> return drawDelete(canvas, ink)
            k.code == Codes.EMOJI || k.code == Codes.GLOBE -> {
                iconLine.color = ink; iconSolid.color = ink
                return Icons.draw(canvas, if (k.code == Codes.EMOJI) "smile" else "globe",
                                  rect.centerX(), rect.centerY(), 22 * density, iconLine, iconSolid)
            }
        }
        val text = face(k)
        val letter = k.code == 0 && text.length == 1
        label.color = ink
        label.textSize = (if (letter) 24 else if (text.length > 3) 15 else 17) * density
        label.typeface = if (letter) letterFace else Typeface.DEFAULT
        val cy = rect.centerY() - (label.descent() + label.ascent()) / 2
        canvas.drawText(text, rect.centerX(), cy, label)
    }

    /** The shift arrow, outlined; filled while caps lock is on. */
    private fun drawShift(canvas: Canvas, color: Int, lock: Boolean) {
        val u = 4.2f * density
        val cx = rect.centerX(); val cy = rect.centerY()
        path.reset()
        path.moveTo(cx, cy - 2.4f * u); path.lineTo(cx + 2.2f * u, cy); path.lineTo(cx + u, cy)
        path.lineTo(cx + u, cy + 1.8f * u); path.lineTo(cx - u, cy + 1.8f * u); path.lineTo(cx - u, cy)
        path.lineTo(cx - 2.2f * u, cy); path.close()
        stroke.color = color
        canvas.drawPath(path, stroke)
        if (lock) {
            fill.color = color
            canvas.drawPath(path, fill)
            canvas.drawRect(cx - u, cy + 2.4f * u, cx + u, cy + 2.4f * u + 2 * density, fill)
        }
    }

    /** The delete key: a tag pointing left with a cross in it. */
    private fun drawDelete(canvas: Canvas, color: Int) {
        val u = 4.2f * density
        val cx = rect.centerX() + 0.3f * u; val cy = rect.centerY()
        stroke.color = color
        path.reset()
        path.moveTo(cx - 1.4f * u, cy - 1.6f * u); path.lineTo(cx + 2.4f * u, cy - 1.6f * u)
        path.lineTo(cx + 2.4f * u, cy + 1.6f * u); path.lineTo(cx - 1.4f * u, cy + 1.6f * u)
        path.lineTo(cx - 3f * u, cy); path.close()
        path.moveTo(cx - 0.2f * u, cy - 0.7f * u); path.lineTo(cx + 1.2f * u, cy + 0.7f * u)
        path.moveTo(cx + 1.2f * u, cy - 0.7f * u); path.lineTo(cx - 0.2f * u, cy + 0.7f * u)
        canvas.drawPath(path, stroke)
    }

    private fun face(k: Key): String = when (k.code) {
        Codes.ENTER -> enterLabel ?: "return"
        Codes.SPACE -> spaceLabel
        // lowercase until shift is on, like iOS: the keys show what they type
        0 -> if (k.label.length == 1 && shift != Shift.OFF) k.label.uppercase() else k.label
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
