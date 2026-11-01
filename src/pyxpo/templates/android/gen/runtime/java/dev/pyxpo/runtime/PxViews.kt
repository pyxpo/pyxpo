package dev.pyxpo.runtime

import android.content.Context
import android.view.View
import android.view.ViewGroup
import android.view.ViewOutlineProvider
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
    private val box = android.graphics.Rect()

    // The keyboard shrank the scroll view (a KeyboardAvoidingView around it): bring the focused field back on
    // screen once the engine has placed the content. ScrollView's own check misses fields the keys now cover.
    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        if (h < oldh) post {
            val f = findFocus()
            if (f != null && f !== this && f.isShown) {
                f.getDrawingRect(box); offsetDescendantRectToMyCoords(f, box)
                val d = computeScrollDeltaToGetChildRectOnScreen(box)
                if (d != 0) smoothScrollBy(0, d)
            }
        }
    }
    override fun onInterceptTouchEvent(e: android.view.MotionEvent) = userScroll && super.onInterceptTouchEvent(e)
    override fun onTouchEvent(e: android.view.MotionEvent) = userScroll && super.onTouchEvent(e)
    override fun dispatchDraw(canvas: android.graphics.Canvas) {
        canvas.save(); canvas.clipRect(scrollX, scrollY, scrollX + width, scrollY + height)
        super.dispatchDraw(canvas); canvas.restore()
    }
}

class PxHScroll(ctx: Context) : android.widget.HorizontalScrollView(ctx), PxScrollable {
    override var userScroll = true
    // RTL: the list starts at its right end, and the part shown keeps its distance from the right edge when the
    // content grows (the content is mirrored inside it, so new items appear on the left).
    private var fromRight = 0
    var rtl = false
        set(on) {
            if (on == field) return
            field = on
            fromRight = 0
            if (on) requestLayout() else scrollTo(0, 0)
        }

    override fun onLayout(changed: Boolean, l: Int, t: Int, r: Int, b: Int) {
        super.onLayout(changed, l, t, r, b)
        val c = getChildAt(0) ?: return
        if (rtl) scrollTo(maxOf(0, c.width - width - fromRight), 0)
    }
    override fun onScrollChanged(l: Int, t: Int, oldl: Int, oldt: Int) {
        super.onScrollChanged(l, t, oldl, oldt)
        val c = getChildAt(0) ?: return
        fromRight = maxOf(0, c.width - width - l)
    }
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
 * Native stack host. Screens are its children (last = top). Pushes and pops use Material's shared-axis X motion: the
 * new screen slides 30dp and fades in while the old one slides the other way and fades out. Android 14+ shows the
 * system predictive-back preview: during the back swipe the top screen shrinks toward the swipe edge with rounded
 * corners over the screen below, and a released swipe finishes as a pop. Swipes come from the system back gesture
 * only (no own edge drag, which fought gesture navigation). All motion runs on the UI thread, Python not involved.
 */
class PxNav(ctx: Context) : PxGroup(ctx) {
    var animated = true
    /** False turns off the back-swipe preview; Back itself still pops. */
    var gesture = true
    var onPop: (() -> Unit)? = null
    /** Children kept only until their pop animation ends. */
    val lingering = HashSet<View>()

    private val density = ctx.resources.displayMetrics.density
    private val shift get() = 30 * density
    private val emphasized = android.view.animation.PathInterpolator(0.2f, 0f, 0f, 1f)
    private var anim: android.animation.ValueAnimator? = null

    private fun live(): List<View> = (0 until childCount).map { getChildAt(it) }.filter { it !in lingering }

    /** One property set per view; `tween` moves every listed view from where it is now to these values. */
    private class Pose(val tx: Float = 0f, val alpha: Float = 1f, val scale: Float = 1f, val radius: Float = 0f)

    private fun tween(targets: List<Pair<View, Pose>>, ms: Long, fadeOutFirst: View? = null, end: () -> Unit = {}) {
        anim?.end()
        val from = targets.map { (v, _) -> Pose(v.translationX, v.alpha, v.scaleX, radiusOf(v)) }
        anim = android.animation.ValueAnimator.ofFloat(0f, 1f).apply {
            duration = ms
            interpolator = android.view.animation.LinearInterpolator()
            addUpdateListener { a ->
                val t = a.animatedValue as Float
                val e = emphasized.getInterpolation(t)
                targets.forEachIndexed { i, (v, to) ->
                    val f = from[i]
                    // Material fade-through: the leaving screen fades over the first 35%, the arriving one after it.
                    val ft = if (to.alpha < f.alpha) Math.min(1f, t / 0.35f)
                             else if (fadeOutFirst != null) Math.max(0f, (t - 0.35f) / 0.65f) else t
                    v.translationX = f.tx + (to.tx - f.tx) * e
                    v.alpha = f.alpha + (to.alpha - f.alpha) * ft
                    val sc = f.scale + (to.scale - f.scale) * e
                    v.scaleX = sc; v.scaleY = sc
                    setRadius(v, f.radius + (to.radius - f.radius) * e)
                }
            }
            addListener(object : android.animation.AnimatorListenerAdapter() {
                var done = false
                override fun onAnimationEnd(a: android.animation.Animator) {
                    if (done) return
                    done = true
                    if (anim === a) anim = null
                    end()
                }
            })
            start()
        }
    }

    private val radii = HashMap<View, Float>()
    private fun radiusOf(v: View) = radii[v] ?: 0f
    private fun setRadius(v: View, r: Float) {
        if (r <= 0.5f) {
            if (radii.remove(v) != null) { v.clipToOutline = false; v.outlineProvider = ViewOutlineProvider.BACKGROUND }
            return
        }
        if (v !in radii) {
            v.outlineProvider = object : ViewOutlineProvider() {
                override fun getOutline(view: View, o: android.graphics.Outline) {
                    o.setRoundRect(0, 0, view.width, view.height, radii[view] ?: 0f)
                }
            }
            v.clipToOutline = true
        }
        radii[v] = r
        v.invalidateOutline()
    }

    private fun rest(v: View) {
        v.translationX = 0f; v.alpha = 1f; v.scaleX = 1f; v.scaleY = 1f; setRadius(v, 0f)
    }

    fun pushed(v: View) {
        cancelPreview()
        val below = live().let { l -> l.getOrNull(l.indexOf(v) - 1) }
        if (!animated || width <= 0 || below == null) { rest(v); below?.let { it.alpha = 0f }; return }
        v.translationX = shift; v.alpha = 0f
        tween(listOf(v to Pose(), below to Pose(tx = -shift, alpha = 0f)), 300, fadeOutFirst = below)
    }

    /** Returns true when the view stays until its exit animation ends. */
    fun popped(v: View): Boolean {
        val next = live().filter { it !== v }.lastOrNull()
        val top = live().lastOrNull() === v
        previewing = false
        if (!top) return false
        if (!animated || width <= 0) { anim?.end(); next?.let { rest(it) }; return false }
        lingering.add(v)
        val fromPreview = v.scaleX < 1f
        if (next != null && !fromPreview) { next.translationX = -shift; next.alpha = 0f }
        val out = if (fromPreview) Pose(tx = v.translationX, alpha = 0f, scale = v.scaleX, radius = radiusOf(v))
                  else Pose(tx = shift, alpha = 0f)
        val moves = listOfNotNull(v to out, next?.let { it to Pose() })
        tween(moves, if (fromPreview) 200 else 250, fadeOutFirst = v) { lingering.remove(v); setRadius(v, 0f); removeView(v) }
        return true
    }

    // Predictive back (Android 14+), driven by the activity's OnBackAnimationCallback.
    private var previewing = false
    private var previewTop: View? = null

    /** Whether this stack would pop on Back now: it has a screen to go back to and is on screen. */
    fun canPreview() = gesture && animated && width > 0 && isShown && live().size > 1

    fun backStarted() {
        anim?.end()
        val l = live()
        val top = l.lastOrNull() ?: return
        val below = l.getOrNull(l.size - 2) ?: return
        previewing = true
        previewTop = top
        below.translationX = -shift; below.alpha = 1f
    }

    /** `p` 0..1 from the system (already eased); `fromLeft` is the edge the swipe started at. */
    fun backProgressed(p: Float, fromLeft: Boolean) {
        if (!previewing) return
        val l = live()
        val top = previewTop ?: return
        if (l.lastOrNull() !== top) return
        val below = l.getOrNull(l.size - 2)
        val s = 1f - 0.1f * p
        top.scaleX = s; top.scaleY = s
        top.translationX = (if (fromLeft) 1f else -1f) * (width * 0.05f) * p
        setRadius(top, 28 * density * Math.min(1f, p * 4f))
        below?.translationX = -shift * (1f - p)
    }

    fun cancelPreview() {
        if (!previewing) return
        previewing = false
        val l = live()
        val top = previewTop ?: return
        previewTop = null
        if (l.lastOrNull() !== top) return
        val below = l.getOrNull(l.size - 2)
        tween(listOfNotNull(top to Pose(), below?.let { it to Pose(tx = -shift, alpha = 0f) }), 200)
    }

    /** Back was released: Python pops soon (see `popped`). If nothing popped this stack, the preview goes back. */
    fun backInvoked() {
        if (!previewing) return
        val top = previewTop
        postDelayed({ if (previewing && previewTop === top) cancelPreview() }, 500)
    }
}
