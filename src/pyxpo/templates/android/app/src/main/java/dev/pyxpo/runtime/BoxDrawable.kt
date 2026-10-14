package dev.pyxpo.runtime

import android.graphics.Canvas
import android.graphics.ColorFilter
import android.graphics.LinearGradient
import android.graphics.Outline
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PixelFormat
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.drawable.Drawable
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.sin

/** What a box looks like. All sizes in px. Radii order: top-left, top-right, bottom-right, bottom-left. */
class BoxSpec(
    val bg: Int?,
    val gradAngle: Float,
    val gradColors: IntArray?,
    val gradStops: FloatArray?,
    val radii: FloatArray,
    val bw: FloatArray,        // border widths: left, top, right, bottom
    val bc: IntArray,          // border colors: left, top, right, bottom
)

/** Draws background colour or linear gradient, per-corner radii and per-side borders. */
class BoxDrawable(private val spec: BoxSpec) : Drawable() {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val outer = Path()
    private val ring = Path()
    private var w = -1
    private var h = -1

    private fun rrect(path: Path, r: RectF, radii: FloatArray) {
        path.reset()
        val rr = floatArrayOf(radii[0], radii[0], radii[1], radii[1], radii[2], radii[2], radii[3], radii[3])
        // clamp so adjacent radii never exceed a side
        val k = minOf(1f, r.width() / max(1f, max(radii[0] + radii[1], radii[3] + radii[2])),
            r.height() / max(1f, max(radii[0] + radii[3], radii[1] + radii[2])))
        if (k < 1f) for (i in rr.indices) rr[i] *= k
        path.addRoundRect(r, rr, Path.Direction.CW)
    }

    override fun onBoundsChange(b: android.graphics.Rect) {
        w = -1
    }

    private fun build() {
        val b = bounds
        if (b.width() == w && b.height() == h) return
        w = b.width(); h = b.height()
        val r = RectF(b)
        rrect(outer, r, spec.radii)
        ring.reset()
        if (spec.bw.any { it > 0f }) {
            val ir = RectF(r.left + spec.bw[0], r.top + spec.bw[1], r.right - spec.bw[2], r.bottom - spec.bw[3])
            if (ir.width() > 0 && ir.height() > 0) {
                val inner = Path()
                val ri = floatArrayOf(max(0f, spec.radii[0] - max(spec.bw[0], spec.bw[1])),
                    max(0f, spec.radii[1] - max(spec.bw[2], spec.bw[1])),
                    max(0f, spec.radii[2] - max(spec.bw[2], spec.bw[3])),
                    max(0f, spec.radii[3] - max(spec.bw[0], spec.bw[3])))
                rrect(inner, ir, ri)
                ring.set(outer)
                ring.op(inner, Path.Op.DIFFERENCE)
            } else ring.set(outer)
        }
    }

    override fun draw(c: Canvas) {
        build()
        val b = bounds
        if (b.isEmpty) return
        val g = spec.gradColors
        if (g != null) {
            val a = Math.toRadians(spec.gradAngle.toDouble())
            val dx = sin(a).toFloat(); val dy = (-cos(a)).toFloat()
            val len = abs(b.width() * dx) + abs(b.height() * dy)
            val cx = b.exactCenterX(); val cy = b.exactCenterY()
            paint.shader = LinearGradient(cx - dx * len / 2, cy - dy * len / 2, cx + dx * len / 2, cy + dy * len / 2,
                g, spec.gradStops, Shader.TileMode.CLAMP)
            paint.style = Paint.Style.FILL
            c.drawPath(outer, paint)
            paint.shader = null
        } else if (spec.bg != null) {
            paint.style = Paint.Style.FILL
            paint.color = spec.bg
            c.drawPath(outer, paint)
        }
        if (!ring.isEmpty) {
            paint.style = Paint.Style.FILL
            if (spec.bc.all { it == spec.bc[0] }) {
                paint.color = spec.bc[0]
                c.drawPath(ring, paint)
            } else {
                c.save()
                c.clipPath(ring)
                val l = b.left.toFloat(); val t = b.top.toFloat(); val r = b.right.toFloat(); val bt = b.bottom.toFloat()
                val bw = spec.bw
                fun poly(color: Int, vararg p: Float) {
                    val path = Path()
                    path.moveTo(p[0], p[1])
                    for (i in 2 until p.size step 2) path.lineTo(p[i], p[i + 1])
                    path.close()
                    paint.color = color
                    c.drawPath(path, paint)
                }
                poly(spec.bc[1], l, t, r, t, r - bw[2], t + bw[1], l + bw[0], t + bw[1])
                poly(spec.bc[2], r, t, r, bt, r - bw[2], bt - bw[3], r - bw[2], t + bw[1])
                poly(spec.bc[3], l, bt, r, bt, r - bw[2], bt - bw[3], l + bw[0], bt - bw[3])
                poly(spec.bc[0], l, t, l, bt, l + bw[0], bt - bw[3], l + bw[0], t + bw[1])
                c.restore()
            }
        }
    }

    override fun getOutline(o: Outline) {
        build()
        if (!outer.isEmpty) o.setConvexPath(outer)
        o.alpha = 1f
    }

    override fun setAlpha(a: Int) { paint.alpha = a }
    override fun setColorFilter(f: ColorFilter?) { paint.colorFilter = f }
    @Suppress("OVERRIDE_DEPRECATION")
    override fun getOpacity() = PixelFormat.TRANSLUCENT
}
