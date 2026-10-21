package dev.pyxpo.modules.keyboard

import android.animation.ObjectAnimator
import android.animation.ValueAnimator
import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RadialGradient
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.SystemClock
import android.text.TextUtils
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.min
import kotlin.math.sqrt

/** `a` moved towards `b` by `t` (0..1), per channel. */
internal fun blend(a: Int, b: Int, t: Float): Int {
    fun ch(x: Int, y: Int) = (x + (y - x) * t).toInt().coerceIn(0, 255)
    return Color.argb(ch(Color.alpha(a), Color.alpha(b)), ch(Color.red(a), Color.red(b)),
                      ch(Color.green(a), Color.green(b)), ch(Color.blue(a), Color.blue(b)))
}

/**
 * The app's panel in place of the keys (`show_panel_async`): a title, a microphone orb that pulses with the
 * voice, text cards, chips and buttons, all from a spec. Taps go to [onEvent] as (type, id); the app answers by
 * showing the next spec. Rendering again keeps the orb's animation and the scroll position.
 */
@SuppressLint("ViewConstructor")
class PanelView(context: Context, private val palette: Palette, private val onEvent: (String, String) -> Unit) :
    LinearLayout(context) {

    private val dp = resources.displayMetrics.density
    private val small = OrbView(context, palette)
    private val big = OrbView(context, palette)
    private val title = text(15f, palette.text, bold = true)
    private val headerHint = text(12f, palette.muted)
    private val bigHint = text(13f, palette.muted).apply { gravity = Gravity.CENTER }
    private val bigBox = LinearLayout(context)
    private val cards = LinearLayout(context)
    private val chips = LinearLayout(context)
    private val chipScroll = HorizontalScrollView(context)
    private val actions = LinearLayout(context)
    private val pulses = ArrayList<ValueAnimator>()
    private var orbId = ""

    init {
        orientation = VERTICAL
        background = GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM,
                                      intArrayOf(blend(palette.background, palette.accent, 0.10f), palette.background))
        val px = { v: Int -> (v * dp).toInt() }

        val heading = LinearLayout(context).apply {
            orientation = VERTICAL
            gravity = Gravity.CENTER_VERTICAL
            addView(title)
            addView(headerHint)
        }
        title.maxLines = 1
        title.ellipsize = TextUtils.TruncateAt.END
        headerHint.maxLines = 1
        headerHint.ellipsize = TextUtils.TruncateAt.END
        val close = pill("ABC", filled = false).apply {
            contentDescription = "Back to the keys"
            setOnClickListener { onEvent("close", "") }
        }
        small.setOnClickListener { onEvent("orb", orbId) }
        addView(LinearLayout(context).apply {
            orientation = HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(px(10), px(4), px(8), 0)
            addView(small, LayoutParams(px(38), px(38)).apply { marginEnd = px(8) })
            addView(heading, LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { marginStart = px(4) })
            addView(close, LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, px(32)))
        }, LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, px(46)))

        big.setOnClickListener { onEvent("orb", orbId) }
        bigBox.apply {
            orientation = VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            addView(big, LayoutParams(px(132), px(132)))
            addView(bigHint, LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        }
        cards.orientation = VERTICAL
        val content = LinearLayout(context).apply {
            orientation = VERTICAL
            setPadding(px(10), px(2), px(10), px(6))
            addView(bigBox, LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
            addView(cards, LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        }
        addView(ScrollView(context).apply { isVerticalScrollBarEnabled = false; addView(content) },
                LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))

        chips.orientation = HORIZONTAL
        chips.gravity = Gravity.CENTER_VERTICAL
        chips.setPadding(px(8), 0, px(8), 0)
        chipScroll.isHorizontalScrollBarEnabled = false
        chipScroll.addView(chips)
        addView(chipScroll, LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, px(42)))

        actions.orientation = HORIZONTAL
        actions.setPadding(px(7), px(4), px(7), px(8))
        addView(actions, LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, px(56)))
    }

    fun setLevel(level: Float) {
        small.setLevel(level)
        big.setLevel(level)
    }

    fun render(spec: JSONObject) {
        for (a in pulses) a.cancel()
        pulses.clear()
        title.text = spec.optString("title", "")
        val hint = spec.optString("hint", "")
        val orb = spec.optJSONObject("orb")
        orbId = orb?.optString("id", "") ?: ""
        val state = orb?.optString("state", "idle") ?: "idle"
        small.state = state
        big.state = state

        val sections = spec.optJSONArray("sections") ?: JSONArray()
        cards.removeAllViews()
        var filled = false
        for (i in 0 until sections.length()) {
            val s = sections.optJSONObject(i) ?: continue
            if (s.optString("text").isNotEmpty() || s.optBoolean("busy")) filled = true
            cards.addView(card(s), LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                .apply { topMargin = (8 * dp).toInt() })
        }
        // nothing written yet: the big orb holds the middle; then it moves into the header and the cards take over
        val centred = orb != null && !filled
        bigBox.visibility = if (centred) View.VISIBLE else View.GONE
        small.visibility = if (orb != null && !centred) View.VISIBLE else View.GONE
        bigHint.text = hint
        headerHint.text = if (centred) "" else hint
        headerHint.visibility = if (headerHint.text.isEmpty()) View.GONE else View.VISIBLE

        val chipList = spec.optJSONArray("chips") ?: JSONArray()
        chips.removeAllViews()
        for (i in 0 until chipList.length()) {
            val c = chipList.optJSONObject(i) ?: continue
            val id = c.optString("id")
            val v = pill(c.optString("label"), filled = c.optBoolean("active")).apply {
                setOnClickListener { onEvent("chip", id) }
            }
            if (c.optBoolean("busy")) pulse(v)
            chips.addView(v, LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, (32 * dp).toInt()).apply {
                marginEnd = (6 * dp).toInt()
            })
        }
        chipScroll.visibility = if (chips.childCount > 0) View.VISIBLE else View.GONE

        val actionList = spec.optJSONArray("actions") ?: JSONArray()
        actions.removeAllViews()
        for (i in 0 until actionList.length()) {
            val a = actionList.optJSONObject(i) ?: continue
            val id = a.optString("id")
            val primary = a.optBoolean("primary")
            actions.addView(TextView(context).apply {
                text = a.optString("label")
                gravity = Gravity.CENTER
                maxLines = 1
                ellipsize = TextUtils.TruncateAt.END
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
                setTextColor(if (primary) palette.onAccent else palette.text)
                if (primary) setTypeface(typeface, Typeface.BOLD)
                background = GradientDrawable().apply {
                    cornerRadius = 12 * dp
                    setColor(if (primary) palette.accent else palette.card)
                }
                setOnClickListener { onEvent("action", id) }
            }, LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, if (primary) 1.4f else 1f).apply {
                marginStart = (3 * dp).toInt(); marginEnd = (3 * dp).toInt()
            })
        }
        actions.visibility = if (actions.childCount > 0) View.VISIBLE else View.GONE
    }

    override fun onDetachedFromWindow() {
        for (a in pulses) a.cancel()
        pulses.clear()
        super.onDetachedFromWindow()
    }

    private fun card(s: JSONObject): View {
        val id = s.optString("id")
        val busy = s.optBoolean("busy")
        val body = s.optString("text")
        val label = text(11f, palette.accent, bold = true).apply {
            text = s.optString("label").uppercase()
            letterSpacing = 0.08f
        }
        val head = LinearLayout(context).apply {
            orientation = HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(label, LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            val action = s.optString("action")
            if (action.isNotEmpty()) addView(text(12f, palette.accent, bold = true).apply { text = action })
        }
        val words = text(16f, if (body.isEmpty()) palette.muted else palette.text).apply {
            text = body.ifEmpty { s.optString("placeholder").ifEmpty { if (busy) "• • •" else "" } }
            setLineSpacing(2 * dp, 1f)
            setPadding(0, (4 * dp).toInt(), 0, 0)
        }
        if (busy) pulse(words)
        return LinearLayout(context).apply {
            orientation = VERTICAL
            val p = (12 * dp).toInt()
            setPadding(p, (10 * dp).toInt(), p, p)
            background = GradientDrawable().apply { cornerRadius = 14 * dp; setColor(palette.card) }
            elevation = 1.5f * dp
            addView(head)
            addView(words)
            if (s.optString("action").isNotEmpty()) {
                isClickable = true
                setOnClickListener { onEvent("section", id) }
            }
        }
    }

    private fun pulse(v: View) {
        pulses.add(ObjectAnimator.ofFloat(v, "alpha", 1f, 0.35f).apply {
            duration = 650
            repeatMode = ValueAnimator.REVERSE
            repeatCount = ValueAnimator.INFINITE
            start()
        })
    }

    private fun text(sp: Float, color: Int, bold: Boolean = false) = TextView(context).apply {
        setTextSize(TypedValue.COMPLEX_UNIT_SP, sp)
        setTextColor(color)
        if (bold) setTypeface(typeface, Typeface.BOLD)
    }

    private fun pill(label: String, filled: Boolean) = TextView(context).apply {
        text = label
        gravity = Gravity.CENTER
        maxLines = 1
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
        setTextColor(if (filled) palette.onAccent else palette.text)
        setTypeface(typeface, if (filled) Typeface.BOLD else Typeface.NORMAL)
        setPadding((14 * dp).toInt(), 0, (14 * dp).toInt(), 0)
        background = GradientDrawable().apply {
            cornerRadius = 16 * dp
            setColor(if (filled) palette.accent else palette.card)
            if (!filled) setStroke((1 * dp).toInt(), blend(palette.card, palette.muted, 0.35f))
        }
    }
}

/**
 * The microphone: a round button that pulses rings with the voice while `listening`, spins while `working`
 * and turns red on `error`. Draws its icons, so no emoji font or image is needed.
 */
@SuppressLint("ViewConstructor")
class OrbView(context: Context, private val palette: Palette) : View(context) {
    var state = "idle"
        set(v) { field = v; contentDescription = DESCRIPTIONS[v] ?: DESCRIPTIONS["idle"]; invalidate() }
    private val dp = resources.displayMetrics.density
    private var target = 0f
    private var level = 0f
    private val born = SystemClock.uptimeMillis()
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND }
    private val rect = RectF()
    private var shader: RadialGradient? = null
    private var shaderKey = 0L

    init {
        isClickable = true
        contentDescription = DESCRIPTIONS["idle"]
    }

    /** The voice's loudness, 0..1 (pyxpo-speech sends ten a second). */
    fun setLevel(l: Float) {
        target = l.coerceIn(0f, 1f)
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        val cx = width / 2f
        val cy = height / 2f
        val outer = min(cx, cy)
        val r = outer * 0.6f
        val t = (SystemClock.uptimeMillis() - born) / 1000f
        val color = if (state == "error") ERROR else palette.accent
        level += (target - level) * 0.22f
        target *= 0.96f   // falls back between the level events, so the halo breathes with the voice

        if (state == "listening") {
            val v = sqrt(level)
            fill.shader = null
            fill.color = color
            fill.alpha = 46
            canvas.drawCircle(cx, cy, r + (outer - r) * (0.25f + 0.75f * v), fill)
            stroke.color = color
            stroke.strokeWidth = 1.6f * dp
            for (i in 0..1) {
                val p = (t * 0.6f + i * 0.5f) % 1f
                stroke.alpha = ((1f - p) * 150).toInt()
                canvas.drawCircle(cx, cy, r + (outer - r) * p, stroke)
            }
        }
        // a soft shadow, then the core lit from the top left
        fill.shader = null
        fill.color = Color.BLACK
        fill.alpha = 34
        canvas.drawCircle(cx, cy + 2.5f * dp, r, fill)
        val key = (width.toLong() shl 40) or (height.toLong() shl 20) or (color.toLong() and 0xFFFFF)
        if (shader == null || key != shaderKey) {
            shader = RadialGradient(cx - r * 0.35f, cy - r * 0.4f, r * 1.7f, blend(color, Color.WHITE, 0.32f),
                                    blend(color, Color.BLACK, 0.12f), Shader.TileMode.CLAMP)
            shaderKey = key
        }
        fill.shader = shader
        fill.alpha = 255
        canvas.drawCircle(cx, cy, r, fill)
        fill.shader = null

        if (state == "working") {
            stroke.color = color
            stroke.alpha = 255
            stroke.strokeWidth = 3f * dp
            val g = r + 5f * dp
            rect.set(cx - g, cy - g, cx + g, cy + g)
            canvas.drawArc(rect, (t * 300f) % 360f, 110f, false, stroke)
        }

        fill.color = palette.onAccent
        if (state == "listening") {
            val s = r * 0.28f
            rect.set(cx - s, cy - s, cx + s, cy + s)
            canvas.drawRoundRect(rect, s * 0.3f, s * 0.3f, fill)
        } else {
            mic(canvas, cx, cy, r)
        }
        if (state == "listening" || state == "working" || level > 0.01f) postInvalidateOnAnimation()
    }

    private fun mic(canvas: Canvas, cx: Float, cy: Float, r: Float) {
        val w = r * 0.17f
        rect.set(cx - w, cy - r * 0.48f, cx + w, cy + r * 0.12f)
        canvas.drawRoundRect(rect, w, w, fill)
        stroke.color = palette.onAccent
        stroke.alpha = 255
        stroke.strokeWidth = r * 0.085f
        rect.set(cx - r * 0.32f, cy - r * 0.26f, cx + r * 0.32f, cy + r * 0.28f)
        canvas.drawArc(rect, 0f, 180f, false, stroke)
        canvas.drawLine(cx, cy + r * 0.28f, cx, cy + r * 0.44f, stroke)
        canvas.drawLine(cx - r * 0.17f, cy + r * 0.44f, cx + r * 0.17f, cy + r * 0.44f, stroke)
    }

    companion object {
        private const val ERROR = 0xFFE5534B.toInt()
        private val DESCRIPTIONS = mapOf("idle" to "Start speaking", "listening" to "Stop listening",
                                         "working" to "Working", "error" to "Try again")
    }
}
