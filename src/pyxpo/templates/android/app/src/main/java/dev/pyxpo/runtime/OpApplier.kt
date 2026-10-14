package dev.pyxpo.runtime

import android.content.Context
import android.content.res.ColorStateList
import android.content.res.Configuration
import android.graphics.Typeface
import android.os.Build
import android.text.Editable
import android.text.TextUtils
import android.text.TextWatcher
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.View.MeasureSpec
import android.view.ViewGroup
import android.widget.*
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * Applies JSON op batches (wire v2) on the UI thread. Styles arrive normalized (dp, ARGB ints).
 * Layout is done by the shared C engine; this class only places frames, measures leaves and paints boxes.
 */
class OpApplier(
    private val ctx: Context,
    private val container: ViewGroup,
    private val sendEvent: (String) -> Unit,
) {
    companion object {
        private const val CONTENT = 0x40000000  // id bit for a ScrollView's synthetic content node
        private val LEAVES = setOf("Text", "Button", "TextInput", "Image")

        /** Env snapshot for the Python side. Sizes in dp. */
        fun envJson(ctx: Context, wPx: Int, hPx: Int): JSONObject {
            val dm = ctx.resources.displayMetrics
            val cfg = ctx.resources.configuration
            val w = Math.round(wPx / dm.density * 100.0) / 100.0
            val h = Math.round(hPx / dm.density * 100.0) / 100.0
            val dark = (cfg.uiMode and Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES
            return JSONObject()
                .put("os", "android")
                .put("window", JSONObject().put("width", w).put("height", h))
                .put("screen", JSONObject().put("width", dm.widthPixels / dm.density.toDouble())
                    .put("height", dm.heightPixels / dm.density.toDouble()))
                .put("scale", dm.density.toDouble())
                .put("font_scale", cfg.fontScale.toDouble())
                .put("color_scheme", if (dark) "dark" else "light")
        }
    }

    private val views = HashMap<Int, View>()
    private val types = HashMap<Int, String>()
    private val styles = HashMap<Int, JSONObject>()
    private val frames = HashMap<Int, FloatArray>()      // last frame in dp: x, y, w, h
    private val pads = HashMap<Int, IntArray>()          // leaf padding+border in px: l, t, r, b
    private val painted = HashSet<Int>()
    private val defaultText = HashMap<Int, ColorStateList>()
    private val propIds = HashMap<String, Int>()
    private val suppress = HashSet<View>()
    private val d: Float get() = ctx.resources.displayMetrics.density
    private val layout = NativeLayout { id, w, wm, h, hm -> measure(id, w, wm, h, hm) }
    private var rootW = 0
    private var rootH = 0
    private var sentEnv: String? = null
    private var batching = false

    init {
        // Root id 1 is implicit in the ops protocol: it is never created by the reconciler.
        val root = PxRoot(ctx) { w, h -> onRootSize(w, h) }
        container.addView(root, ViewGroup.LayoutParams(-1, -1))
        views[1] = root
        types[1] = "Root"
    }

    // -- ops ---------------------------------------------------------------------------------------
    fun apply(batch: String) {
        val ops = JSONArray(batch)
        batching = true
        for (i in 0 until ops.length()) {
            val o = ops.getJSONObject(i)
            when (o.getString("op")) {
                "create" -> create(o.getInt("id"), o.getString("type"), o.optJSONObject("props") ?: JSONObject())
                "update" -> update(o.getInt("id"), o.optJSONObject("props") ?: JSONObject(), o.optJSONArray("removed"))
                "insert" -> insert(o.getInt("parent"), o.getInt("id"), o.getInt("index"))
                "remove" -> remove(o.getInt("parent"), o.getInt("id"))
                "delete" -> delete(o.getInt("id"))
            }
        }
        batching = false
        flush()
    }

    private fun event(name: String, id: Int, payload: JSONObject = JSONObject()) {
        sendEvent(JSONObject().put("event", name).put("id", id).put("payload", payload).toString())
    }

    private fun create(id: Int, type: String, props: JSONObject) {
        val v: View = when (type) {
            "Text" -> TextView(ctx).also { it.includeFontPadding = false }
            "Button" -> Button(ctx).also {
                it.minWidth = 0; it.minHeight = 0; it.minimumWidth = 0; it.minimumHeight = 0
                it.stateListAnimator = null
                it.setOnClickListener { event("press", id) }
            }
            "Image" -> ImageView(ctx)
            "TextInput" -> EditText(ctx)
            "ScrollView" -> ScrollView(ctx).also { it.addView(PxGroup(ctx), ViewGroup.LayoutParams(-2, -2)) }
            else -> PxGroup(ctx)
        }
        views[id] = v
        types[id] = type
        if (v is TextView) defaultText[id] = v.textColors
        layout.create(id)
        if (type in LEAVES) layout.setMeasured(id, true)
        if (type == "ScrollView") {
            layout.create(id or CONTENT)
            layout.insert(id, id or CONTENT, 0)
            layout.setNum(id or CONTENT, prop("flex_shrink"), 0f)
        }
        update(id, props, null)
        if (type == "TextInput") (v as EditText).addTextChangedListener(object : TextWatcher {
            override fun afterTextChanged(s: Editable?) {
                if (v in suppress) return
                event("change_text", id, JSONObject().put("value", s.toString()))
            }
            override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
            override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
        })
    }

    private fun update(id: Int, props: JSONObject, removed: JSONArray?) {
        val v = views[id] ?: return
        val r = HashSet<String>()
        if (removed != null) for (i in 0 until removed.length()) r.add(removed.getString(i))
        if ("style" in r) applyStyle(id, v, JSONObject())
        var textDirty = false
        if ("spans" in r) { spans.remove(id); textDirty = true }
        val keys = props.keys()
        while (keys.hasNext()) {
            val k = keys.next()
            when (k) {
                "text" -> if (v is TextView && v !is EditText) { texts[id] = props.optString(k); textDirty = true }
                "spans" -> if (v is TextView && v !is EditText) { spans[id] = props.optJSONArray(k); textDirty = true }
                "value" -> (v as? EditText)?.let {
                    if (it.text.toString() != props.optString(k)) {
                        suppress.add(it); it.setText(props.optString(k)); it.setSelection(it.text.length)
                        suppress.remove(it)
                        layout.markDirty(id)
                    }
                }
                "placeholder" -> (v as? EditText)?.hint = props.optString(k)
                "style" -> applyStyle(id, v, props.optJSONObject(k) ?: JSONObject())
            }
        }
        if (textDirty && v is TextView) { applyText(id, v); layout.markDirty(id) }
        if (!batching) flush()
    }

    private val texts = HashMap<Int, String>()
    private val spans = HashMap<Int, JSONArray?>()
    private val fontCache = HashMap<String, Typeface?>()

    private fun applyText(id: Int, v: TextView) {
        val sp = spans[id]
        val t = texts[id] ?: ""
        if (sp == null || sp.length() == 0) { v.text = t; return }
        val b = android.text.SpannableStringBuilder()
        val dm = ctx.resources.displayMetrics
        for (i in 0 until sp.length()) {
            val o = sp.getJSONObject(i)
            val st = o.optJSONObject("style") ?: JSONObject()
            val from = b.length
            b.append(o.optString("text"))
            val to = b.length
            if (to == from) continue
            fun span(w: Any) = b.setSpan(w, from, to, android.text.Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            if (st.has("color")) span(android.text.style.ForegroundColorSpan(col(st, "color")))
            if (st.has("background_color")) span(android.text.style.BackgroundColorSpan(col(st, "background_color")))
            if (st.has("font_size")) span(android.text.style.AbsoluteSizeSpan(
                TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_SP, st.optDouble("font_size").toFloat(), dm).roundToInt()))
            if (st.has("font_weight") || st.has("font_style") || st.has("font_family")) {
                val tf = typefaceFor(st)
                if (Build.VERSION.SDK_INT >= 28) span(android.text.style.TypefaceSpan(tf))
                else span(android.text.style.StyleSpan(tf.style))
            }
            val deco = st.optString("text_decoration")
            if ("underline" in deco) span(android.text.style.UnderlineSpan())
            if ("line-through" in deco) span(android.text.style.StrikethroughSpan())
        }
        v.text = b
    }

    /** Typeface from font_file (custom), font_family (generic name) plus weight and italic. */
    private fun typefaceFor(s: JSONObject): Typeface {
        val w = s.opt("font_weight")?.toString() ?: "normal"
        val weight = when (w) { "bold" -> 700; "normal" -> 400; else -> w.toIntOrNull() ?: 400 }
        val italic = s.optString("font_style") == "italic"
        val file = s.optString("font_file")
        val fam = s.optString("font_family")
        val base: Typeface = when {
            file.isNotEmpty() -> fontCache.getOrPut(file) {
                try { Typeface.createFromFile(file) } catch (e: Exception) { null }
            } ?: Typeface.DEFAULT
            fam == "monospace" || fam == "serif" || fam == "sans-serif" -> Typeface.create(fam, Typeface.NORMAL)
            else -> Typeface.DEFAULT
        }
        return if (Build.VERSION.SDK_INT >= 28) Typeface.create(base, weight, italic)
        else Typeface.create(base, (if (weight >= 600) 1 else 0) or (if (italic) 2 else 0))
    }

    private fun insert(parent: Int, id: Int, index: Int) {
        val g = groupOf(parent) ?: return
        val v = views[id] ?: return
        (v.parent as? ViewGroup)?.removeView(v)
        g.addView(v, min(index, g.childCount), ViewGroup.LayoutParams(-2, -2))
        layout.remove(parentNode(parent), id)
        layout.insert(parentNode(parent), id, index)
    }

    private fun remove(parent: Int, id: Int) {
        val v = views[id] ?: return
        groupOf(parent)?.removeView(v)
        layout.remove(parentNode(parent), id)
    }

    private fun delete(id: Int) {
        val v = views.remove(id)
        texts.remove(id); spans.remove(id)
        (v?.parent as? ViewGroup)?.removeView(v)
        if (types.remove(id) == "ScrollView") layout.delete(id or CONTENT)
        layout.delete(id)
        styles.remove(id); frames.remove(id); pads.remove(id); painted.remove(id); defaultText.remove(id)
    }

    private fun parentNode(parent: Int) = if (types[parent] == "ScrollView") parent or CONTENT else parent

    private fun groupOf(parent: Int): ViewGroup? {
        val p = views[parent] ?: return null
        return if (p is ScrollView) p.getChildAt(0) as ViewGroup else p as? ViewGroup
    }

    // -- style -------------------------------------------------------------------------------------
    private fun prop(name: String): Int = propIds.getOrPut(name) { layout.propId(name) }

    private fun applyStyle(id: Int, v: View, s: JSONObject) {
        val old = styles[id] ?: JSONObject()
        val it = s.keys()
        while (it.hasNext()) {
            val k = it.next()
            val nv = s.get(k)
            if (old.opt(k)?.toString() != nv.toString()) pushLayout(id, k, nv)
        }
        val ok = old.keys()
        while (ok.hasNext()) {
            val k = ok.next()
            if (!s.has(k)) { val p = prop(k); if (p >= 0) layout.reset(id, p) }
        }
        styles[id] = s
        paint(id, v, s)
        layout.markDirty(id)
    }

    private fun pushLayout(id: Int, k: String, v: Any) {
        val p = prop(k)
        if (p < 0) return
        when (v) {
            is Number -> layout.setNum(id, p, v.toFloat())
            is String -> layout.setStr(id, p, v)
        }
    }

    private fun num(s: JSONObject, k: String, def: Double = 0.0) = s.optDouble(k, def)
    private fun col(s: JSONObject, k: String) = s.getLong(k).toInt()
    private fun px(dp: Double) = (dp * d).toFloat()

    private fun paint(id: Int, v: View, s: JSONObject) {
        // leaf views draw their own content, so padding + border become native padding
        if (types[id] in LEAVES) {
            fun e(side: String) = ((num(s, "padding_$side") + num(s, "border_${side}_width")) * d).roundToInt()
            val p = intArrayOf(e("left"), e("top"), e("right"), e("bottom"))
            pads[id] = p
            v.setPadding(p[0], p[1], p[2], p[3])
        }
        paintBox(id, v, s)
        val clip = s.optString("overflow") == "hidden"
        v.clipToOutline = clip && id in painted
        (v as? PxGroup)?.clipChildren = clip
        v.alpha = num(s, "opacity", 1.0).toFloat().coerceIn(0f, 1f)
        paintShadow(v, s)
        v.rotation = num(s, "rotate").toFloat()
        v.scaleX = (num(s, "scale", 1.0) * num(s, "scale_x", 1.0)).toFloat()
        v.scaleY = (num(s, "scale", 1.0) * num(s, "scale_y", 1.0)).toFloat()
        v.translationX = px(num(s, "translate_x"))
        v.translationY = px(num(s, "translate_y"))
        if (v is TextView) paintText(id, v, s)
    }

    private fun paintBox(id: Int, v: View, s: JSONObject) {
        val radii = floatArrayOf(px(num(s, "border_top_left_radius")), px(num(s, "border_top_right_radius")),
            px(num(s, "border_bottom_right_radius")), px(num(s, "border_bottom_left_radius")))
        val sides = arrayOf("left", "top", "right", "bottom")
        val bw = FloatArray(4) { px(num(s, "border_${sides[it]}_width")).let { w -> if (w > 0f) max(1f, w.roundToInt().toFloat()) else 0f } }
        val bc = IntArray(4) { if (s.has("border_${sides[it]}_color")) col(s, "border_${sides[it]}_color") else 0xFF000000.toInt() }
        val grad = s.optJSONObject("linear_gradient")
        val hasBox = s.has("background_color") || grad != null || radii.any { it > 0f } || bw.any { it > 0f }
        if (hasBox) {
            var colors: IntArray? = null
            var stops: FloatArray? = null
            if (grad != null) {
                val c = grad.getJSONArray("colors"); val st = grad.getJSONArray("stops")
                colors = IntArray(c.length()) { c.getLong(it).toInt() }
                stops = FloatArray(st.length()) { st.getDouble(it).toFloat() }
            }
            v.background = BoxDrawable(BoxSpec(if (s.has("background_color")) col(s, "background_color") else null,
                grad?.optDouble("angle", 180.0)?.toFloat() ?: 0f, colors, stops, radii, bw, bc))
            painted.add(id)
        } else if (painted.remove(id)) v.background = null
    }

    /** Shadow via elevation: radius/offset map to elevation, colour to the shadow tint (API 28+). */
    private fun paintShadow(v: View, s: JSONObject) {
        val op = num(s, "shadow_opacity", if (s.has("shadow_radius") || s.has("shadow_color")) 1.0 else 0.0)
        val elev = max(num(s, "elevation"), if (op > 0.0) num(s, "shadow_radius") else 0.0)
        v.elevation = (elev * d).toFloat()
        if (Build.VERSION.SDK_INT >= 28) {
            val base = if (s.has("shadow_color")) col(s, "shadow_color") else 0xFF000000.toInt()
            val a = ((base ushr 24) * op.coerceIn(0.0, 1.0)).roundToInt()
            val c = (a shl 24) or (base and 0xFFFFFF)
            v.outlineAmbientShadowColor = c
            v.outlineSpotShadowColor = c
        }
    }

    private fun paintText(id: Int, v: TextView, s: JSONObject) {
        if (s.has("color")) v.setTextColor(col(s, "color")) else defaultText[id]?.let { v.setTextColor(it) }
        val size = num(s, "font_size", 14.0)
        val scaled = !s.has("allow_font_scaling") || s.optBoolean("allow_font_scaling", true)
        v.setTextSize(if (scaled) TypedValue.COMPLEX_UNIT_SP else TypedValue.COMPLEX_UNIT_DIP, size.toFloat())
        v.typeface = typefaceFor(s)
        if (s.has("text_shadow_color") || s.has("text_shadow_radius"))
            v.setShadowLayer((num(s, "text_shadow_radius", 0.0) * d).toFloat(), (num(s, "text_shadow_offset_x") * d).toFloat(),
                (num(s, "text_shadow_offset_y") * d).toFloat(), if (s.has("text_shadow_color")) col(s, "text_shadow_color") else 0xFF000000.toInt())
        else v.setShadowLayer(0f, 0f, 0f, 0)
        val h = when (s.optString("text_align")) {
            "center" -> Gravity.CENTER_HORIZONTAL
            "right" -> Gravity.END
            else -> Gravity.START
        }
        v.gravity = h or (if (v is EditText || v is Button) Gravity.CENTER_VERTICAL else Gravity.TOP)
        val lines = num(s, "number_of_lines", 0.0).toInt()
        v.maxLines = if (lines > 0) lines else Int.MAX_VALUE
        v.ellipsize = if (lines > 0) TextUtils.TruncateAt.END else null
        if (Build.VERSION.SDK_INT >= 28 && s.has("line_height")) v.lineHeight = (num(s, "line_height") * d).roundToInt()
        v.letterSpacing = if (s.has("letter_spacing") && size > 0) (num(s, "letter_spacing") / size).toFloat() else 0f
        var flags = v.paintFlags and (android.graphics.Paint.UNDERLINE_TEXT_FLAG or android.graphics.Paint.STRIKE_THRU_TEXT_FLAG).inv()
        val deco = s.optString("text_decoration")
        if ("underline" in deco) flags = flags or android.graphics.Paint.UNDERLINE_TEXT_FLAG
        if ("line-through" in deco) flags = flags or android.graphics.Paint.STRIKE_THRU_TEXT_FLAG
        v.paintFlags = flags
    }

    // -- layout ------------------------------------------------------------------------------------
    /** Leaf measure callback from the engine. w/h are inner sizes in dp. Returns packed float bits (w, h). */
    private fun measure(id: Int, w: Float, wm: Int, h: Float, hm: Int): Long {
        val v = views[id] ?: return 0L
        val p = pads[id] ?: IntArray(4)
        fun spec(size: Float, mode: Int, pad: Int): Int = when {
            mode == 2 || size.isNaN() || size > 1e6f -> MeasureSpec.makeMeasureSpec(0, MeasureSpec.UNSPECIFIED)
            mode == 0 -> MeasureSpec.makeMeasureSpec(max(0, (size * d).roundToInt()) + pad, MeasureSpec.EXACTLY)
            else -> MeasureSpec.makeMeasureSpec(max(0, (size * d).roundToInt()) + pad, MeasureSpec.AT_MOST)
        }
        v.measure(spec(w, wm, p[0] + p[2]), spec(h, hm, p[1] + p[3]))
        val mw = max(0, v.measuredWidth - p[0] - p[2]) / d
        val mh = max(0, v.measuredHeight - p[1] - p[3]) / d
        return (java.lang.Float.floatToRawIntBits(mw).toLong() shl 32) or
            (java.lang.Float.floatToRawIntBits(mh).toLong() and 0xffffffffL)
    }

    private fun onRootSize(w: Int, h: Int) {
        if (w <= 0 || h <= 0 || (w == rootW && h == rootH)) return
        rootW = w; rootH = h
        sendEnv()
        flush()
    }

    /** Sends the current window/scale/color scheme to Python when it changed. */
    fun sendEnv() {
        if (rootW <= 0) return
        val j = envJson(ctx, rootW, rootH)
        j.remove("os")
        val s = j.toString()
        if (s == sentEnv) return
        sentEnv = s
        event("env", 0, j)
    }

    /** Call after a configuration change (density, font scale, dark mode, rotation). */
    fun configChanged() {
        sendEnv()
        for ((id, t) in types) if (t in LEAVES) layout.markDirty(id)
        flush(force = true)
    }

    private fun flush(force: Boolean = false) {
        if (rootW <= 0) return
        val touched = HashSet<Int>()
        layout.calc(rootW / d, rootH / d) { id, x, y, w, h -> place(id, floatArrayOf(x, y, w, h), touched) }
        if (force) for ((id, f) in frames) place(id, f, touched)
        for (id in touched) {
            val v = views[id] ?: continue
            val f = frames[id] ?: continue
            placeView(v, f)
        }
    }

    private fun place(id: Int, f: FloatArray, touched: HashSet<Int>) {
        if (id == 1) return
        if (id and CONTENT != 0) {
            val base = id and CONTENT.inv()
            val c = (views[base] as? ScrollView)?.getChildAt(0) as? PxGroup ?: return
            c.fw = (f[2] * d).roundToInt(); c.fh = (f[3] * d).roundToInt()
            frames[id] = f
            touched.add(base)
            return
        }
        val v = views[id] ?: return
        frames[id] = f
        if (v is ScrollView) touched.add(id) else placeView(v, f)
    }

    private fun placeView(v: View, f: FloatArray) {
        val l = (f[0] * d).roundToInt(); val t = (f[1] * d).roundToInt()
        val r = ((f[0] + f[2]) * d).roundToInt(); val b = ((f[1] + f[3]) * d).roundToInt()
        v.measure(MeasureSpec.makeMeasureSpec(r - l, MeasureSpec.EXACTLY), MeasureSpec.makeMeasureSpec(b - t, MeasureSpec.EXACTLY))
        v.layout(l, t, r, b)
    }
}
