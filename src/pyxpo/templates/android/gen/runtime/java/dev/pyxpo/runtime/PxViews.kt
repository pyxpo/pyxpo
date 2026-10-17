package dev.pyxpo.runtime

import android.content.Context
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout

/** Container whose children are positioned by [OpApplier] from the shared layout engine, never by Android. */
open class PxGroup(ctx: Context) : ViewGroup(ctx) {
    /** Forced size in px (ScrollView content). -1 = follow the measure spec. */
    var fw = -1
    var fh = -1

    /** React Native pointerEvents: "auto", "none" (no touches here or below), "box-only" (children get none),
     *  "box-none" (the default for a group without handlers: touches fall through to what is behind). */
    var pointerEvents = "auto"

    init { clipChildren = false }

    override fun dispatchTouchEvent(e: android.view.MotionEvent) = pointerEvents != "none" && super.dispatchTouchEvent(e)
    override fun onInterceptTouchEvent(e: android.view.MotionEvent) =
        pointerEvents == "box-only" || super.onInterceptTouchEvent(e)

    override fun onMeasure(wSpec: Int, hSpec: Int) {
        setMeasuredDimension(
            if (fw >= 0) fw else View.MeasureSpec.getSize(wSpec),
            if (fh >= 0) fh else View.MeasureSpec.getSize(hSpec),
        )
    }

    override fun onLayout(changed: Boolean, l: Int, t: Int, r: Int, b: Int) {}
}

/**
 * Hosts a module view. Its [PxGroup] parent never lays children out, so a relayout the module view asks for
 * (a camera preview adding its surface, for example) runs here at the frame the engine gave.
 */
class PxViewFrame(ctx: Context, child: View) : FrameLayout(ctx) {
    private val relayout: Runnable? = Runnable {
        measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(height, View.MeasureSpec.EXACTLY))
        layout(left, top, right, bottom)
    }

    init { addView(child, LayoutParams(-1, -1)) }

    override fun requestLayout() {
        super.requestLayout()
        relayout?.let { removeCallbacks(it); post(it) }  // null while FrameLayout's constructor runs
    }
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

/**
 * Native stack host. Screens are its children (last = top). Pushes slide in from the right over a parallax-shifted
 * previous screen, pops slide out, and an edge drag pops interactively. All motion runs on the UI/render thread
 * through ViewPropertyAnimator, so Python is not in the loop while a transition plays.
 */
class PxNav(ctx: Context) : PxGroup(ctx) {
    var animated = true
    var gesture = true
    var onPop: (() -> Unit)? = null
    /** Children kept only until their pop animation ends. */
    val lingering = HashSet<View>()

    private val density = ctx.resources.displayMetrics.density
    private val slop = android.view.ViewConfiguration.get(ctx).scaledTouchSlop
    private val ease = android.view.animation.PathInterpolator(0.2f, 0.8f, 0.2f, 1f)
    private var edgeDown = false
    private var dragging = false
    private var downX = 0f
    private var downY = 0f
    private var vt: android.view.VelocityTracker? = null

    private fun live(): List<View> = (0 until childCount).map { getChildAt(it) }.filter { it !in lingering }
    private fun parallax(w: Int) = w * 0.25f

    fun pushed(v: View) {
        val below = live().let { l -> l.getOrNull(l.indexOf(v) - 1) }
        if (!animated || width <= 0 || below == null) return
        val w = width
        v.translationX = w.toFloat()
        v.animate().translationX(0f).setDuration(320).setInterpolator(ease).start()
        below.animate().translationX(-parallax(w)).setDuration(320).setInterpolator(ease).start()
    }

    /** Returns true when the view stays until its exit animation ends. */
    fun popped(v: View): Boolean {
        val w = width
        if (!animated || w <= 0 || v.translationX >= w * 0.99f) return false
        lingering.add(v)
        v.animate().translationX(w.toFloat()).setDuration(260).setInterpolator(ease)
            .withEndAction { lingering.remove(v); removeView(v) }.start()
        live().lastOrNull()?.animate()?.translationX(0f)?.setDuration(260)?.setInterpolator(ease)?.start()
        return true
    }

    override fun onInterceptTouchEvent(e: android.view.MotionEvent): Boolean {
        if (!gesture) return false
        when (e.actionMasked) {
            android.view.MotionEvent.ACTION_DOWN -> {
                edgeDown = live().size > 1 && e.x < 24 * density
                downX = e.x; downY = e.y
                vt?.recycle(); vt = android.view.VelocityTracker.obtain(); vt?.addMovement(e)
            }
            android.view.MotionEvent.ACTION_MOVE -> if (edgeDown) {
                vt?.addMovement(e)
                val dx = e.x - downX
                if (dx > slop && dx > Math.abs(e.y - downY)) {
                    dragging = true
                    parent?.requestDisallowInterceptTouchEvent(true)
                    return true
                }
            }
            android.view.MotionEvent.ACTION_UP, android.view.MotionEvent.ACTION_CANCEL -> edgeDown = false
        }
        return false
    }

    override fun onTouchEvent(e: android.view.MotionEvent): Boolean {
        if (!dragging) return false
        vt?.addMovement(e)
        val l = live()
        val top = l.lastOrNull() ?: return true
        val below = l.getOrNull(l.size - 2)
        val w = width.toFloat()
        val dx = Math.max(0f, Math.min(w, e.x - downX))
        when (e.actionMasked) {
            android.view.MotionEvent.ACTION_MOVE -> {
                top.translationX = dx
                below?.translationX = -parallax(width) * (1f - dx / w)
            }
            android.view.MotionEvent.ACTION_UP, android.view.MotionEvent.ACTION_CANCEL -> {
                dragging = false; edgeDown = false
                vt?.computeCurrentVelocity(1000)
                val vx = vt?.xVelocity ?: 0f
                val commit = e.actionMasked == android.view.MotionEvent.ACTION_UP && (dx > w * 0.35f || (vx > 900f * density && dx > 24 * density))
                if (commit) {
                    top.animate().translationX(w).setDuration(180).setInterpolator(ease).withEndAction { onPop?.invoke() }.start()
                    below?.animate()?.translationX(0f)?.setDuration(180)?.setInterpolator(ease)?.start()
                } else {
                    top.animate().translationX(0f).setDuration(200).setInterpolator(ease).start()
                    below?.animate()?.translationX(-parallax(width))?.setDuration(200)?.setInterpolator(ease)?.start()
                }
            }
        }
        return true
    }
}
