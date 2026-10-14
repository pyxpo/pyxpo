package dev.pyxpo.runtime

import android.content.Context
import android.view.View
import android.view.ViewGroup

/** Container whose children are positioned by [OpApplier] from the shared layout engine, never by Android. */
open class PxGroup(ctx: Context) : ViewGroup(ctx) {
    /** Forced size in px (ScrollView content). -1 = follow the measure spec. */
    var fw = -1
    var fh = -1

    init { clipChildren = false }

    override fun onMeasure(wSpec: Int, hSpec: Int) {
        setMeasuredDimension(
            if (fw >= 0) fw else View.MeasureSpec.getSize(wSpec),
            if (fh >= 0) fh else View.MeasureSpec.getSize(hSpec),
        )
    }

    override fun onLayout(changed: Boolean, l: Int, t: Int, r: Int, b: Int) {}
}

/** Root view: reports its pixel size so the engine can lay out against the real window. */
class PxRoot(ctx: Context, private val onSize: (Int, Int) -> Unit) : PxGroup(ctx) {
    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        onSize(w, h)
    }
}

/** Scroll views whose touch handling can be switched off (`scroll_enabled=False`). */
interface PxScrollable { var userScroll: Boolean }

class PxScroll(ctx: Context) : android.widget.ScrollView(ctx), PxScrollable {
    override var userScroll = true
    override fun onInterceptTouchEvent(e: android.view.MotionEvent) = userScroll && super.onInterceptTouchEvent(e)
    override fun onTouchEvent(e: android.view.MotionEvent) = userScroll && super.onTouchEvent(e)
    override fun dispatchDraw(canvas: android.graphics.Canvas) {
        canvas.save(); canvas.clipRect(scrollX, scrollY, scrollX + width, scrollY + height)
        super.dispatchDraw(canvas); canvas.restore()
    }
}

class PxHScroll(ctx: Context) : android.widget.HorizontalScrollView(ctx), PxScrollable {
    override var userScroll = true
    override fun onInterceptTouchEvent(e: android.view.MotionEvent) = userScroll && super.onInterceptTouchEvent(e)
    override fun onTouchEvent(e: android.view.MotionEvent) = userScroll && super.onTouchEvent(e)
    override fun dispatchDraw(canvas: android.graphics.Canvas) {
        canvas.save(); canvas.clipRect(scrollX, scrollY, scrollX + width, scrollY + height)
        super.dispatchDraw(canvas); canvas.restore()
    }
}

/** Vector shape: replays move/line/cubic/close commands scaled from a `viewbox` square to the view size. */
class PxPath(ctx: Context) : View(ctx) {
    private val path = android.graphics.Path()
    private val strokePaint = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG).apply {
        style = android.graphics.Paint.Style.STROKE
        strokeCap = android.graphics.Paint.Cap.ROUND
        strokeJoin = android.graphics.Paint.Join.ROUND
    }
    private val fillPaint = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG)
    private var viewBox = 24f
    private var strokeWidth = 2f
    private var hasStroke = false
    private var hasFill = false

    fun setCommands(cmds: org.json.JSONArray?) {
        path.reset()
        if (cmds != null) for (i in 0 until cmds.length()) {
            val c = cmds.getJSONArray(i)
            val f = { k: Int -> c.getDouble(k).toFloat() }
            when (c.getInt(0)) {
                0 -> path.moveTo(f(1), f(2))
                1 -> path.lineTo(f(1), f(2))
                2 -> path.cubicTo(f(1), f(2), f(3), f(4), f(5), f(6))
                3 -> path.close()
            }
        }
        invalidate()
    }

    fun setBox(b: Float) { viewBox = b; invalidate() }
    fun setStrokeWidth(w: Float) { strokeWidth = w; invalidate() }
    fun setStroke(c: Int?) { hasStroke = c != null; if (c != null) strokePaint.color = c; invalidate() }
    fun setFill(c: Int?) { hasFill = c != null; if (c != null) fillPaint.color = c; invalidate() }

    override fun onDraw(canvas: android.graphics.Canvas) {
        val s = minOf(width, height) / viewBox
        canvas.save()
        canvas.translate((width - viewBox * s) / 2, (height - viewBox * s) / 2)
        canvas.scale(s, s)
        strokePaint.strokeWidth = strokeWidth
        if (hasFill) canvas.drawPath(path, fillPaint)
        if (hasStroke) canvas.drawPath(path, strokePaint)
        canvas.restore()
    }
}
