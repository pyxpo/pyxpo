package dev.pyxpo.modules.keyboard

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.view.View

/**
 * Line icons drawn on a 24-unit grid, so they stay crisp at any size and take the theme's colour (an emoji
 * keeps its own colours and looks pasted on). Names match `ICONS` in the Python package.
 */
object Icons {
    val NAMES = setOf("mic", "sparkles", "globe", "smile", "settings")

    private val path = Path()
    private val oval = RectF()

    /** Draws `name` centred on (cx, cy), `size` px wide; `line` strokes, `solid` fills dots and stars. */
    fun draw(canvas: Canvas, name: String, cx: Float, cy: Float, size: Float, line: Paint, solid: Paint) {
        val u = size / 24f
        val x0 = cx - 12 * u
        val y0 = cy - 12 * u
        fun x(v: Float) = x0 + v * u
        fun y(v: Float) = y0 + v * u
        fun circle(px: Float, py: Float, r: Float, p: Paint) = canvas.drawCircle(x(px), y(py), r * u, p)
        when (name) {
            "mic" -> {
                oval.set(x(9f), y(2.5f), x(15f), y(14.5f))
                canvas.drawRoundRect(oval, 3 * u, 3 * u, line)
                oval.set(x(5.5f), y(5f), x(18.5f), y(18f))
                canvas.drawArc(oval, 0f, 180f, false, line)
                canvas.drawLine(x(12f), y(18f), x(12f), y(21.5f), line)
                canvas.drawLine(x(8.5f), y(21.5f), x(15.5f), y(21.5f), line)
            }
            "sparkles" -> {
                star(x(10f), y(14f), 7.5f * u)
                canvas.drawPath(path, solid)
                star(x(18.5f), y(5.5f), 3.5f * u)
                canvas.drawPath(path, solid)
            }
            "globe" -> {
                circle(12f, 12f, 9f, line)
                oval.set(x(8f), y(3f), x(16f), y(21f))
                canvas.drawOval(oval, line)
                canvas.drawLine(x(3f), y(12f), x(21f), y(12f), line)
            }
            "smile" -> {
                circle(12f, 12f, 9f, line)
                circle(9f, 10f, 1.2f, solid)
                circle(15f, 10f, 1.2f, solid)
                oval.set(x(8f), y(9f), x(16f), y(16.5f))
                canvas.drawArc(oval, 25f, 130f, false, line)
            }
            "settings" -> {   // three sliders
                for ((row, knob) in listOf(6f to 15f, 12f to 8f, 18f to 13f)) {
                    canvas.drawLine(x(3.5f), y(row), x(20.5f), y(row), line)
                    circle(knob, row, 2.3f, solid)
                }
            }
        }
    }

    /** A four-pointed star with curved sides, like the AI sparkle. */
    private fun star(cx: Float, cy: Float, r: Float) {
        val k = 0.18f * r
        path.reset()
        path.moveTo(cx, cy - r)
        path.quadTo(cx + k, cy - k, cx + r, cy)
        path.quadTo(cx + k, cy + k, cx, cy + r)
        path.quadTo(cx - k, cy + k, cx - r, cy)
        path.quadTo(cx - k, cy - k, cx, cy - r)
        path.close()
    }

    fun line(density: Float) = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE; strokeWidth = 1.8f * density; strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND
    }

    fun solid() = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL }
}

/** One icon in a view: a toolbar button. `round` draws a filled circle behind it (an active button). */
@SuppressLint("ViewConstructor")
class IconView(context: Context, private val name: String, private val ink: Int, private val round: Int? = null) : View(context) {
    private val density = resources.displayMetrics.density
    private val line = Icons.line(density).apply { color = ink }
    private val solid = Icons.solid().apply { color = ink }
    private val disc = Paint(Paint.ANTI_ALIAS_FLAG)

    override fun onDraw(canvas: Canvas) {
        val cx = width / 2f
        val cy = height / 2f
        round?.let {
            disc.color = it
            canvas.drawCircle(cx, cy, minOf(width, height) / 2f - 2 * density, disc)
        }
        Icons.draw(canvas, name, cx, cy, 22 * density, line, solid)
    }
}
