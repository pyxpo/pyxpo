package dev.pyxpo.runtime

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Matrix
import android.graphics.RectF
import android.view.GestureDetector
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.VelocityTracker
import android.view.ViewConfiguration
import android.view.animation.DecelerateInterpolator
import android.widget.ImageView
import android.widget.OverScroller
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/**
 * An image that fits the view and zooms with pinch and double tap, pans and flings while zoomed, and hands
 * sideways drags to the pager at the image edges. At fit size a vertical drag moves it for swipe-to-close:
 * [onDrag] gets how far (0 to 1 of the view height), [onRelease] whether to close and which way.
 */
internal class ZoomImageView(context: Context) : ImageView(context) {
    var maxZoom = 4f
    var doubleTapZoom = true
    var swipeToClose = true
    var onTap: (() -> Unit)? = null
    var onDrag: ((Float) -> Unit)? = null
    var onRelease: ((dismiss: Boolean, direction: Float) -> Unit)? = null

    private val m = Matrix()
    private val values = FloatArray(9)
    private val rect = RectF()
    private var fitScale = 1f
    private val scroller = OverScroller(context)
    private var animator: ValueAnimator? = null
    private val slop = ViewConfiguration.get(context).scaledTouchSlop
    private val density = resources.displayMetrics.density
    private var tracker: VelocityTracker? = null
    private var downX = 0f
    private var downY = 0f
    private var dragging = false
    private var multi = false

    init {
        scaleType = ScaleType.MATRIX
    }

    private val scaleDetector = ScaleGestureDetector(context, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
        override fun onScaleBegin(d: ScaleGestureDetector): Boolean {
            stopMotion()
            return drawable != null
        }

        override fun onScale(d: ScaleGestureDetector): Boolean {
            val target = (zoom() * d.scaleFactor).coerceIn(0.75f, maxZoom * 1.15f)
            val f = target / zoom()
            m.postScale(f, f, d.focusX, d.focusY)
            constrain()
            return true
        }

        override fun onScaleEnd(d: ScaleGestureDetector) {
            val z = zoom()
            if (z < 1f) animateZoom(1f, width / 2f, height / 2f)
            else if (z > maxZoom) animateZoom(maxZoom, d.focusX, d.focusY)
        }
    })

    private val gestures = GestureDetector(context, object : GestureDetector.SimpleOnGestureListener() {
        override fun onDown(e: MotionEvent): Boolean {
            stopMotion()
            return true
        }

        override fun onSingleTapConfirmed(e: MotionEvent): Boolean {
            onTap?.invoke()
            return true
        }

        override fun onSingleTapUp(e: MotionEvent): Boolean {
            if (!doubleTapZoom) onTap?.invoke()
            return doubleTapZoom
        }

        override fun onDoubleTap(e: MotionEvent): Boolean {
            if (!doubleTapZoom || drawable == null) return false
            if (zoom() > 1.01f) animateZoom(1f, e.x, e.y) else animateZoom(min(maxZoom, 2.5f), e.x, e.y)
            return true
        }

        override fun onScroll(e1: MotionEvent?, e2: MotionEvent, dx: Float, dy: Float): Boolean {
            if (zoom() <= 1.01f || scaleDetector.isInProgress) return false
            mapped()
            val atEdge = (dx < 0 && rect.left >= -0.5f) || (dx > 0 && rect.right <= width + 0.5f)
            if (atEdge && abs(dx) > abs(dy) && e2.pointerCount == 1) {
                parent?.requestDisallowInterceptTouchEvent(false)  // let the pager take the drag
                return false
            }
            m.postTranslate(-dx, -dy)
            constrain()
            return true
        }

        override fun onFling(e1: MotionEvent?, e2: MotionEvent, vx: Float, vy: Float): Boolean {
            if (zoom() <= 1.01f) return false
            mapped()
            val minX = min(width - rect.width(), 0f).toInt()
            val minY = min(height - rect.height(), 0f).toInt()
            val startX = rect.left.toInt()
            val startY = rect.top.toInt()
            scroller.fling(startX, startY, vx.toInt(), vy.toInt(), minX, 0, minY, 0)
            var lastX = startX
            var lastY = startY
            postOnAnimation(object : Runnable {
                override fun run() {
                    if (!scroller.computeScrollOffset()) return
                    m.postTranslate((scroller.currX - lastX).toFloat(), (scroller.currY - lastY).toFloat())
                    lastX = scroller.currX
                    lastY = scroller.currY
                    constrain()
                    postOnAnimation(this)
                }
            })
            return true
        }
    })

    /** Zoom relative to fit size: 1 is the whole image on screen. */
    fun zoom(): Float {
        m.getValues(values)
        return if (fitScale > 0f) values[Matrix.MSCALE_X] / fitScale else 1f
    }

    fun reset() {
        stopMotion()
        fit()
    }

    override fun setImageBitmap(bm: android.graphics.Bitmap?) {
        super.setImageBitmap(bm)
        fit()
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        fit()
    }

    private fun fit() {
        val d = drawable
        m.reset()
        if (d == null || width == 0 || height == 0 || d.intrinsicWidth <= 0 || d.intrinsicHeight <= 0) {
            imageMatrix = m
            return
        }
        val dw = d.intrinsicWidth.toFloat()
        val dh = d.intrinsicHeight.toFloat()
        fitScale = min(width / dw, height / dh)
        m.setScale(fitScale, fitScale)
        m.postTranslate((width - dw * fitScale) / 2f, (height - dh * fitScale) / 2f)
        imageMatrix = m
    }

    private fun mapped(): RectF {
        val d = drawable
        rect.set(0f, 0f, (d?.intrinsicWidth ?: 0).toFloat(), (d?.intrinsicHeight ?: 0).toFloat())
        m.mapRect(rect)
        return rect
    }

    /** Keeps the image covering the view where it is bigger, centered where it is smaller. */
    private fun constrain() {
        mapped()
        val dx = when {
            rect.width() <= width -> (width - rect.width()) / 2f - rect.left
            rect.left > 0 -> -rect.left
            rect.right < width -> width - rect.right
            else -> 0f
        }
        val dy = when {
            rect.height() <= height -> (height - rect.height()) / 2f - rect.top
            rect.top > 0 -> -rect.top
            rect.bottom < height -> height - rect.bottom
            else -> 0f
        }
        m.postTranslate(dx, dy)
        imageMatrix = m
    }

    private fun animateZoom(target: Float, fx: Float, fy: Float) {
        stopMotion()
        val from = zoom()
        animator = ValueAnimator.ofFloat(from, target).apply {
            duration = 240
            interpolator = DecelerateInterpolator()
            addUpdateListener {
                val f = (it.animatedValue as Float) / zoom()
                m.postScale(f, f, fx, fy)
                constrain()
            }
            start()
        }
    }

    private fun stopMotion() {
        animator?.cancel()
        animator = null
        if (!scroller.isFinished) scroller.forceFinished(true)
    }

    override fun onTouchEvent(e: MotionEvent): Boolean {
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                downX = e.rawX
                downY = e.rawY
                dragging = false
                multi = false
                tracker?.recycle()
                tracker = VelocityTracker.obtain()
                // While zoomed this view pans; the pager takes over only at the image edges (see onScroll).
                parent?.requestDisallowInterceptTouchEvent(zoom() > 1.01f)
            }
            MotionEvent.ACTION_POINTER_DOWN -> {
                multi = true
                parent?.requestDisallowInterceptTouchEvent(true)
            }
        }
        tracker?.addMovement(e)
        if (handleDrag(e)) return true
        scaleDetector.onTouchEvent(e)
        gestures.onTouchEvent(e)
        if (e.actionMasked == MotionEvent.ACTION_UP || e.actionMasked == MotionEvent.ACTION_CANCEL) {
            tracker?.recycle()
            tracker = null
        }
        return true
    }

    /** Swipe-to-close at fit size: a mostly vertical one-finger drag. */
    private fun handleDrag(e: MotionEvent): Boolean {
        if (!swipeToClose) return false
        val dy = e.rawY - downY
        when (e.actionMasked) {
            MotionEvent.ACTION_MOVE -> {
                if (!dragging && !multi && zoom() <= 1.01f && !scaleDetector.isInProgress &&
                    abs(dy) > slop && abs(dy) > abs(e.rawX - downX) * 1.2f) {
                    dragging = true
                    parent?.requestDisallowInterceptTouchEvent(true)
                }
                if (dragging) {
                    translationY = dy
                    onDrag?.invoke(abs(dy) / max(height * 0.6f, 1f))
                    return true
                }
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                if (!dragging) return false
                dragging = false
                val t = tracker
                t?.computeCurrentVelocity(1000)
                val vy = t?.yVelocity ?: 0f
                t?.recycle()
                tracker = null
                val dismiss = e.actionMasked == MotionEvent.ACTION_UP &&
                    (abs(dy) > 120 * density || abs(vy) > 1000 * density)
                onRelease?.invoke(dismiss, if (dy != 0f) dy else vy)
                return true
            }
        }
        return dragging
    }
}
