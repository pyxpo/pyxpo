package dev.pyxpo.runtime

import android.animation.Animator
import android.animation.AnimatorListenerAdapter
import android.animation.ValueAnimator
import android.app.Activity
import android.app.Dialog
import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.ColorDrawable
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.util.TypedValue
import android.view.Gravity
import android.view.MotionEvent
import android.view.VelocityTracker
import android.view.View
import android.view.ViewConfiguration
import android.view.ViewGroup
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.view.WindowManager
import android.view.animation.DecelerateInterpolator
import android.widget.FrameLayout
import android.widget.ProgressBar
import android.widget.TextView
import dev.pyxpo.moduleapi.PxModule
import dev.pyxpo.moduleapi.PxModuleContext
import dev.pyxpo.moduleapi.PxReply
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.abs
import kotlin.math.roundToInt

/** Modules built into the runtime (no package needed), then the ones listed in [tool.pyxpo] modules. */
val allModules: List<PxModule> by lazy { listOf<PxModule>(ImageViewerModule()) + pxModules }

/**
 * Full-screen image viewer: a pager of [ZoomImageView] pages in a full-screen dialog. Pinch or double-tap to zoom,
 * swipe sideways to page, swipe down, press Back or tap the close button to leave. The `open` reply comes when the
 * viewer closes, with the index it closed on; page changes go to Python as `ImageViewer.index` events.
 */
class ImageViewerModule : PxModule() {
    override val name = "ImageViewer"

    override fun call(ctx: PxModuleContext, method: String, args: JSONArray, reply: PxReply) {
        when (method) {
            "open" -> {
                val uris = args.optJSONArray(0)?.let { a -> (0 until a.length()).mapNotNull { a.optString(it).ifEmpty { null } } }.orEmpty()
                if (uris.isEmpty()) { reply(null, "no images to show"); return }
                val o = args.optJSONObject(1) ?: JSONObject()
                val a = ctx.activity
                a.runOnUiThread {
                    if (current != null) { reply(null, "an image viewer is already open"); return@runOnUiThread }
                    if (a.isFinishing) { reply(null, "the activity is closing"); return@runOnUiThread }
                    val d = ViewerDialog(a, uris, o, { ctx.emit("ImageViewer.index", mapOf("index" to it)) }) { i ->
                        current = null
                        reply(mapOf("index" to i), null)
                    }
                    current = d
                    d.show()
                }
            }
            "close" -> ctx.activity.runOnUiThread { current?.close(); reply(null, null) }
            else -> reply(null, "unknown native call ImageViewer.$method")
        }
    }

    companion object {
        private var current: ViewerDialog? = null
    }
}

/**
 * Horizontal pager without androidx: pages sit side by side at `index * width` and the pager scrolls between them.
 * Only the current page and its two neighbours exist; their views are reused as the index moves. A child that is
 * panning a zoomed image keeps the drag by calling `requestDisallowInterceptTouchEvent(true)`.
 */
private class ImagePager(context: Context, private val count: Int, start: Int,
                         private val makePage: () -> View, private val bindPage: (View, Int) -> Unit,
                         private val unbindPage: (View) -> Unit, private val onSelected: (Int) -> Unit) : FrameLayout(context) {
    var index = start
        private set
    private val bound = HashMap<Int, View>()
    private val spare = ArrayList<View>()
    private val slop = ViewConfiguration.get(context).scaledTouchSlop
    private val minFling = ViewConfiguration.get(context).scaledMinimumFlingVelocity * 2
    private var tracker: VelocityTracker? = null
    private var downX = 0f
    private var downY = 0f
    private var lastX = 0f
    private var dragging = false
    private var settle: ValueAnimator? = null

    init {
        bind()
    }

    fun pageAt(i: Int): View? = bound[i]

    /** Keeps views for index - 1 .. index + 1 and reuses the rest. */
    private fun bind() {
        val want = (index - 1..index + 1).filter { it in 0 until count }
        for (i in bound.keys.toList()) if (i !in want) {
            val v = bound.remove(i)!!
            unbindPage(v)
            v.visibility = View.GONE
            spare.add(v)
        }
        for (i in want) if (i !in bound) {
            val v = spare.removeLastOrNull() ?: makePage().also { addView(it, LayoutParams(-1, -1)) }
            v.visibility = View.VISIBLE
            v.tag = i
            bound[i] = v
            bindPage(v, i)
        }
        requestLayout()
    }

    override fun onLayout(changed: Boolean, l: Int, t: Int, r: Int, b: Int) {
        val w = r - l
        for (i in 0 until childCount) {
            val c = getChildAt(i)
            if (c.visibility == View.GONE) continue
            val p = c.tag as? Int ?: continue
            c.layout(p * w, 0, p * w + w, b - t)
        }
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        settle?.cancel()
        scrollTo(index * w, 0)
    }

    override fun onInterceptTouchEvent(e: MotionEvent): Boolean {
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                downX = e.x
                downY = e.y
                lastX = e.x
                dragging = false
                if (settle?.isRunning == true) settle?.end()
                track(e, true)
            }
            MotionEvent.ACTION_MOVE -> {
                track(e, false)
                if (e.pointerCount == 1 && abs(e.x - downX) > slop && abs(e.x - downX) > abs(e.y - downY)) {
                    dragging = true
                    lastX = e.x
                    parent?.requestDisallowInterceptTouchEvent(true)
                }
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> dragging = false
        }
        return dragging
    }

    override fun onTouchEvent(e: MotionEvent): Boolean {
        track(e, e.actionMasked == MotionEvent.ACTION_DOWN)
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> lastX = e.x
            MotionEvent.ACTION_MOVE -> {
                val w = width.coerceAtLeast(1)
                var dx = lastX - e.x
                val x = scrollX + dx
                if (x < 0 || x > (count - 1) * w) dx /= 3  // resist past the first and last page
                scrollBy(dx.roundToInt(), 0)
                lastX = e.x
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                val t = tracker
                t?.computeCurrentVelocity(1000)
                val vx = if (e.actionMasked == MotionEvent.ACTION_UP) t?.xVelocity ?: 0f else 0f
                val w = width.coerceAtLeast(1)
                val target = when {
                    vx < -minFling -> index + 1
                    vx > minFling -> index - 1
                    else -> (scrollX.toFloat() / w).roundToInt()
                }.coerceIn(0, count - 1).coerceIn(index - 1, index + 1)
                dragging = false
                tracker?.recycle()
                tracker = null
                go(target)
            }
        }
        return true
    }

    private fun track(e: MotionEvent, reset: Boolean) {
        if (reset) { tracker?.recycle(); tracker = VelocityTracker.obtain() }
        val t = tracker ?: VelocityTracker.obtain().also { tracker = it }
        // Velocity in the pager's own coordinates: the pager scrolls, so offset by scrollX.
        val ev = MotionEvent.obtain(e)
        ev.offsetLocation(scrollX.toFloat(), 0f)
        t.addMovement(ev)
        ev.recycle()
    }

    private fun go(target: Int) {
        if (target != index) {
            index = target
            bind()
            onSelected(target)
        }
        val to = target * width
        settle?.cancel()
        settle = ValueAnimator.ofInt(scrollX, to).apply {
            duration = 260
            interpolator = DecelerateInterpolator(1.6f)
            addUpdateListener { scrollTo(it.animatedValue as Int, 0) }
            addListener(object : AnimatorListenerAdapter() {
                override fun onAnimationCancel(a: Animator) { scrollTo(to, 0) }
            })
            start()
        }
    }
}

private class ViewerDialog(
    private val activity: Activity,
    private val uris: List<String>,
    o: JSONObject,
    private val onIndex: (Int) -> Unit,
    private val onClose: (Int) -> Unit,
) : Dialog(activity, android.R.style.Theme_Black_NoTitleBar_Fullscreen) {
    private val bgColor = parseColor(o.optString("background", "#000000"))
    private val swipeToClose = o.optBoolean("swipeToClose", true)
    private val doubleTapZoom = o.optBoolean("doubleTapZoom", true)
    private val maxZoom = o.optDouble("maxZoom", 4.0).toFloat().coerceAtLeast(1f)
    private val showCount = o.optBoolean("showCount", true) && uris.size > 1
    private var index = o.optInt("index", 0).coerceIn(0, uris.size - 1)
    private val background = ColorDrawable(bgColor)
    private val root = FrameLayout(activity)
    private val closeButton = TextView(activity)
    private val counter = TextView(activity)
    private val loader = BitmapLoader(activity)
    private val pager = ImagePager(activity, uris.size, index, ::makePage, ::bindPage, ::unbindPage) { position ->
        index = position
        updateCounter()
        for (i in 0 until uris.size) if (i != position) (pagerPage(i))?.image?.reset()
        onIndex(position)
    }
    private var chromeHidden = false
    private var closing = false
    private var finished = false

    init {
        root.background = background
        root.addView(pager, FrameLayout.LayoutParams(-1, -1))

        val size = dp(44)
        closeButton.text = "✕"
        closeButton.setTextColor(Color.WHITE)
        closeButton.textSize = 18f
        closeButton.gravity = Gravity.CENTER
        closeButton.background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(0x29FFFFFF) }
        closeButton.contentDescription = o.optString("closeLabel", "Close").ifEmpty { "Close" }
        closeButton.isClickable = true
        closeButton.isFocusable = true
        closeButton.setOnClickListener { close() }
        root.addView(closeButton, FrameLayout.LayoutParams(size, size, Gravity.TOP or Gravity.START))
        counter.setTextColor(Color.WHITE)
        counter.textSize = 16f
        counter.typeface = Typeface.DEFAULT_BOLD
        counter.gravity = Gravity.CENTER
        counter.visibility = if (showCount) View.VISIBLE else View.GONE
        root.addView(counter, FrameLayout.LayoutParams(-2, size, Gravity.TOP or Gravity.CENTER_HORIZONTAL))
        updateCounter()

        root.setOnApplyWindowInsetsListener { _, insets ->
            val top: Int
            val left: Int
            if (Build.VERSION.SDK_INT >= 30) {
                val i = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
                top = i.top; left = i.left
            } else {
                @Suppress("DEPRECATION")
                top = insets.systemWindowInsetTop
                @Suppress("DEPRECATION")
                left = insets.systemWindowInsetLeft
            }
            (closeButton.layoutParams as FrameLayout.LayoutParams).setMargins(left + dp(16), top + dp(8), 0, 0)
            (counter.layoutParams as FrameLayout.LayoutParams).setMargins(0, top + dp(8), 0, 0)
            closeButton.requestLayout()
            counter.requestLayout()
            insets
        }
        setContentView(root)
        setOnDismissListener { finish() }
        window?.apply {
            setLayout(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
            setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
            setWindowAnimations(0)
            addFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS)
            clearFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN)
            @Suppress("DEPRECATION")
            statusBarColor = Color.TRANSPARENT
            @Suppress("DEPRECATION")
            navigationBarColor = Color.TRANSPARENT
            if (Build.VERSION.SDK_INT >= 28) {
                attributes = attributes.apply {
                    layoutInDisplayCutoutMode = WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES
                }
            }
            if (Build.VERSION.SDK_INT >= 30) {
                setDecorFitsSystemWindows(false)
                insetsController?.setSystemBarsAppearance(0, WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS or
                    WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS)
            } else {
                @Suppress("DEPRECATION")
                decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_LAYOUT_STABLE or
                    View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            }
        }
    }

    override fun show() {
        root.alpha = 0f
        super.show()
        root.animate().alpha(1f).setDuration(180).start()
    }

    /** Fades out, then dismisses. */
    fun close() {
        if (closing) return
        closing = true
        root.animate().alpha(0f).setDuration(160).withEndAction { dismissSafely() }.start()
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() = close()

    private fun dismissSafely() {
        if (isShowing && !activity.isFinishing && !activity.isDestroyed) dismiss() else finish()
    }

    private fun finish() {
        if (finished) return
        finished = true
        loader.shutdown()
        onClose(index)
    }

    private fun updateCounter() {
        counter.text = "${index + 1} / ${uris.size}"
    }

    private fun toggleChrome() {
        chromeHidden = !chromeHidden
        val a = if (chromeHidden) 0f else 1f
        closeButton.animate().alpha(a).setDuration(180).start()
        counter.animate().alpha(a).setDuration(180).start()
        closeButton.isClickable = !chromeHidden
    }

    /** Swipe-to-close drag: fades the background and chrome as the page moves away. */
    private fun dragged(fraction: Float) {
        val fade = 1f - fraction.coerceIn(0f, 1f) * 0.85f
        background.alpha = (fade * 255).toInt()
        val chrome = if (chromeHidden) 0f else fade
        closeButton.alpha = chrome
        counter.alpha = chrome
    }

    private fun released(page: View, dismiss: Boolean, direction: Float) {
        if (dismiss) {
            closing = true
            val h = root.height.toFloat().coerceAtLeast(1f)
            page.animate().translationY(if (direction < 0) -h else h).setDuration(200).start()
            ValueAnimator.ofInt(background.alpha, 0).apply {
                duration = 200
                addUpdateListener { background.alpha = it.animatedValue as Int }
                start()
            }
            closeButton.animate().alpha(0f).setDuration(200).start()
            counter.animate().alpha(0f).setDuration(200).withEndAction { dismissSafely() }.start()
        } else {
            page.animate().translationY(0f).setDuration(220).start()
            ValueAnimator.ofInt(background.alpha, 255).apply {
                duration = 220
                addUpdateListener { background.alpha = it.animatedValue as Int }
                start()
            }
            val chrome = if (chromeHidden) 0f else 1f
            closeButton.animate().alpha(chrome).setDuration(220).start()
            counter.animate().alpha(chrome).setDuration(220).start()
        }
    }

    private fun dp(v: Int) = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v.toFloat(), activity.resources.displayMetrics).toInt()

    private fun pagerPage(i: Int): Page? = pager.pageAt(i) as? Page

    private inner class Page(context: Context) : FrameLayout(context) {
        val image = ZoomImageView(context).apply {
            maxZoom = this@ViewerDialog.maxZoom
            doubleTapZoom = this@ViewerDialog.doubleTapZoom
            swipeToClose = this@ViewerDialog.swipeToClose
            onTap = { toggleChrome() }
            onDrag = { dragged(it) }
            onRelease = { dismiss, direction -> released(this, dismiss, direction) }
        }
        val spinner = ProgressBar(context).apply { isIndeterminate = true }
        val failed = TextView(context).apply {
            text = "Couldn't load this image"
            setTextColor(0xB3FFFFFF.toInt())
            textSize = 15f
            visibility = View.GONE
        }
        var token = 0

        init {
            addView(image, LayoutParams(-1, -1))
            addView(spinner, LayoutParams(-2, -2, Gravity.CENTER))
            addView(failed, LayoutParams(-2, -2, Gravity.CENTER))
        }
    }

    private fun makePage(): View = Page(activity)

    private fun bindPage(v: View, position: Int) {
        val page = v as Page
        page.image.reset()
        page.image.translationY = 0f
        page.image.setImageDrawable(null)
        page.image.contentDescription = if (uris.size > 1) "Image ${position + 1} of ${uris.size}" else "Image"
        page.failed.visibility = View.GONE
        page.spinner.visibility = View.VISIBLE
        val token = ++page.token
        val dm = activity.resources.displayMetrics
        loader.load(uris[position], maxOf(dm.widthPixels, dm.heightPixels) * 2) { bitmap ->
            if (page.token != token) return@load
            page.spinner.visibility = View.GONE
            if (bitmap != null) page.image.setImageBitmap(bitmap) else page.failed.visibility = View.VISIBLE
        }
    }

    private fun unbindPage(v: View) {
        val page = v as Page
        page.token++
        page.image.setImageDrawable(null)
    }

    companion object {
        fun parseColor(s: String): Int = try { Color.parseColor(s) } catch (e: IllegalArgumentException) { Color.BLACK }
    }
}
