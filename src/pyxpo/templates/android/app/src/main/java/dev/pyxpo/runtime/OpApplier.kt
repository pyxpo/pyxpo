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
        private val LEAVES = setOf("Text", "Button", "TextInput", "Image") + PxControls.TYPES

        /** Env snapshot for the Python side. Sizes in dp. */
        fun envJson(ctx: Context, wPx: Int, hPx: Int, ins: IntArray = IntArray(4), kbPx: Int = 0): JSONObject {
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
                .put("insets", JSONObject().put("left", ins[0] / dm.density.toDouble()).put("top", ins[1] / dm.density.toDouble())
                    .put("right", ins[2] / dm.density.toDouble()).put("bottom", ins[3] / dm.density.toDouble()))
                .put("keyboard", JSONObject().put("visible", kbPx > 0).put("height", kbPx / dm.density.toDouble()))
        }
    }

    private val controls = PxControls(ctx) { name, id, payload -> event(name, id, payload) }
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
    private val anim = Animated({ n, id, pl -> event(n, id, pl) }) { touched -> onAnimFrame(touched) }
    private val binds = HashMap<Int, HashMap<String, Int>>()   // view id -> style key -> animated node id
    private val depCache = HashMap<Int, Set<Int>>()

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
                "anode" -> { anim.anode(o.getInt("id"), o.getJSONObject("node")); depCache.clear() }
                "anode_del" -> { anim.anodeDel(o.getInt("id")); depCache.clear() }
                "alisten" -> anim.alisten(o.getInt("id"), o.getBoolean("on"))
                "animate" -> anim.animate(o.getInt("id"), o.getJSONObject("anim"))
                "astop" -> anim.astop(o.getInt("id"))
                "aset" -> anim.aset(o.getJSONObject("vals"))
                "call" -> call(o.getInt("id"), o.getString("module"), o.getString("method"),
                    o.optJSONArray("args") ?: JSONArray(), o.optBoolean("reply"))
            }
        }
        batching = false
        requestFlush()
    }

    private var flushPending = false
    private val flushCb = android.view.Choreographer.FrameCallback { flushPending = false; flush() }

    /** Lays out once per frame no matter how many batches arrived since the last vsync (runs before traversal). */
    private fun requestFlush() {
        if (flushPending) return
        flushPending = true
        android.view.Choreographer.getInstance().postFrameCallback(flushCb)
    }

    private fun event(name: String, id: Int, payload: JSONObject = JSONObject()) {
        sendEvent(JSONObject().put("event", name).put("id", id).put("payload", payload).toString())
    }

    private fun create(id: Int, type: String, props: JSONObject) {
        val v: View = when (type) {
            in PxControls.TYPES -> controls.create(id, type)
            "Text" -> TextView(ctx).also { it.includeFontPadding = false }
            "Button" -> Button(ctx).also {
                it.minWidth = 0; it.minHeight = 0; it.minimumWidth = 0; it.minimumHeight = 0
                it.stateListAnimator = null
                it.setOnClickListener { event("press", id) }
            }
            "Image" -> ImageView(ctx)
            "Path" -> PxPath(ctx)
            "TextInput" -> EditText(ctx)
            "ScrollView" -> (if (props.optBoolean("horizontal")) PxHScroll(ctx) else PxScroll(ctx)).also {
                it.addView(PxGroup(ctx), ViewGroup.LayoutParams(-2, -2))
            }
            "Modal" -> PxGroup(ctx).also { it.isClickable = true; it.isFocusable = true }
            "NavStack" -> PxNav(ctx).also { n -> n.onPop = { event("pop_gesture", id) } }
            else -> PxGroup(ctx)
        }
        views[id] = v
        types[id] = type
        if (v is TextView) defaultText[id] = v.textColors
        layout.create(id)
        if (type in LEAVES) layout.setMeasured(id, true)
        if (type == "ScrollView") {
            layout.setNum(id, prop("scroll"), 1f)
            layout.create(id or CONTENT)
            layout.insert(id, id or CONTENT, 0)
            layout.setNum(id or CONTENT, prop("flex_shrink"), 0f)
            if (props.optBoolean("horizontal")) {
                layout.setStr(id, prop("flex_direction"), "row")
                layout.setStr(id or CONTENT, prop("flex_direction"), "row")
            }
            wireScroll(id, v as FrameLayout)
        }
        update(id, props, null)
        if (type == "TextInput") {
            val e = v as EditText
            e.setOnFocusChangeListener { _, f -> event(if (f) "focus" else "blur", id) }
            e.setOnEditorActionListener { tv, action, _ ->
                event("submit", id, JSONObject().put("value", tv.text.toString()))
                false  // not consumed: the IME still moves focus (Next) or closes (Done)
            }
            wired.add(id)
            if (props.optBoolean("auto_focus")) focusLater(e)
        }
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
        var a11yDirty = r.any { it.startsWith("accessib") }
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
                "on_press", "on_press_in", "on_press_out", "on_long_press" -> if (v !is Button) {
                    pressy.add(id); touchKeys.getOrPut(id) { HashSet() }.add(k); attachTouch(id, v) }
                "on_touch_start", "on_touch_move", "on_touch_end" -> {
                    rawTouch.add(id); touchKeys.getOrPut(id) { HashSet() }.add(k); attachTouch(id, v) }
                "on_request_close" -> closeListeners.add(id)
                "accessibility_label", "accessibility_hint", "accessibility_role", "accessibility_state",
                "accessibility_value", "accessible" -> a11yDirty = true
                "style" -> applyStyle(id, v, props.optJSONObject(k) ?: JSONObject())
                "on_layout" -> layoutListeners.add(id)
                "animated" -> (v as? PxNav)?.animated = props.optBoolean(k, true)
                "gesture" -> (v as? PxNav)?.gesture = props.optBoolean(k, true)
                "source", "resize_mode", "tint_color" -> if (v is ImageView) applyImage(id, v, props, r)
                else -> if (v is PxScrollable) scrollProp(id, v as FrameLayout, k, props)
            }
        }
        for (k in r) {
            if (k == "on_layout") layoutListeners.remove(id)
            if (k == "on_request_close") closeListeners.remove(id)
            if (k.startsWith("on_touch_") || k.startsWith("on_press") || k == "on_long_press") {
                val left = touchKeys[id]?.also { it.remove(k) }
                if (left == null || left.none { it.startsWith("on_touch_") }) rawTouch.remove(id)
                if (left == null || left.none { it.startsWith("on_press") || it == "on_long_press" }) pressy.remove(id)
            }
            if (v is PxScrollable) scrollProp(id, v as FrameLayout, k, null)
            if (v is ImageView && !props.has(k) && (k == "source" || k == "resize_mode" || k == "tint_color")) applyImage(id, v, JSONObject(), r)
        }
        if (v is EditText) applyInput(id, v, props, r)
        if (types[id] in PxControls.TYPES) controls.update(id, v, props, r)
        if (v is PxPath) {
            if (props.has("path")) v.setCommands(props.optJSONArray("path")) else if ("path" in r) v.setCommands(null)
            if (props.has("viewbox")) v.setBox(props.optDouble("viewbox", 24.0).toFloat())
            if (props.has("stroke_width")) v.setStrokeWidth(props.optDouble("stroke_width", 2.0).toFloat())
            if (props.has("stroke")) v.setStroke(props.optLong("stroke").toInt()) else if ("stroke" in r) v.setStroke(null)
            if (props.has("fill")) v.setFill(props.optLong("fill").toInt()) else if ("fill" in r) v.setFill(null)
        }
        if (textDirty && v is TextView) { applyText(id, v); layout.markDirty(id) }
        if (a11yDirty) a11y[id] = (a11y[id] ?: JSONObject()).also { merge(it, props, r) }.also { applyA11y(v, it) }
        if (!batching) flush()
    }

    // -- ScrollView ---------------------------------------------------------------------------------
    private class ScrollCfg {
        var paging = false
        var throttle = 16L
        var ae: JSONObject? = null
        var emit = false
        var onScroll = false
        var begin = false; var end = false; var momentum = false
        var last = 0L
        var dragging = false
        var idle: Runnable? = null
    }

    private val scrolls = HashMap<Int, ScrollCfg>()
    private val layoutListeners = HashSet<Int>()
    private val imgReq = HashMap<Int, String>()
    private val images by lazy { Images(ctx) }
    private val ui = android.os.Handler(android.os.Looper.getMainLooper())

    private fun scrollProp(id: Int, v: FrameLayout, k: String, props: JSONObject?) {
        val c = scrolls[id] ?: return
        val on = props?.opt(k)
        when (k) {
            "paging_enabled" -> c.paging = props?.optBoolean(k) ?: false
            "scroll_enabled" -> (v as PxScrollable).userScroll = props?.optBoolean(k, true) ?: true
            "shows_scroll_indicator" -> {
                val show = props?.optBoolean(k, true) ?: true
                v.isVerticalScrollBarEnabled = show; v.isHorizontalScrollBarEnabled = show
            }
            "bounces" -> v.overScrollMode = if (props?.optBoolean(k, true) ?: true) View.OVER_SCROLL_IF_CONTENT_SCROLLS else View.OVER_SCROLL_NEVER
            "scroll_event_throttle" -> c.throttle = props?.optLong(k, 16) ?: 16
            "on_scroll" -> {
                c.ae = (on as? JSONObject)?.optJSONObject("\$ae")
                c.emit = if (on is JSONObject) on.optBoolean("emit") else on == true
                c.onScroll = on != null
            }
            "on_scroll_begin_drag" -> c.begin = props != null
            "on_scroll_end_drag" -> c.end = props != null
            "on_momentum_scroll_end" -> c.momentum = props != null
        }
    }

    private fun scrollInfo(id: Int, v: FrameLayout): JSONObject {
        val f = frames[id or CONTENT]
        return JSONObject().put("x", v.scrollX / d.toDouble()).put("y", v.scrollY / d.toDouble())
            .put("width", v.width / d.toDouble()).put("height", v.height / d.toDouble())
            .put("content_width", (f?.get(2) ?: 0f).toDouble()).put("content_height", (f?.get(3) ?: 0f).toDouble())
    }

    private fun emitScroll(id: Int, v: FrameLayout, c: ScrollCfg) {
        if (c.emit) event("scroll", id, JSONObject().put("value", scrollInfo(id, v)))
    }

    private fun wireScroll(id: Int, v: FrameLayout) {
        val c = ScrollCfg()
        scrolls[id] = c
        c.idle = Runnable {
            if (v !is PxScrollable) return@Runnable
            if (c.dragging) return@Runnable
            if (c.paging) {
                val horiz = v is PxHScroll
                val page = if (horiz) v.width else v.height
                val pos = if (horiz) v.scrollX else v.scrollY
                if (page > 0) {
                    val target = (Math.round(pos.toFloat() / page) * page)
                    if (target != pos) {
                        if (horiz) (v as PxHScroll).smoothScrollTo(target, 0) else (v as PxScroll).smoothScrollTo(0, target)
                        ui.postDelayed(c.idle!!, 90); return@Runnable
                    }
                }
            }
            emitScroll(id, v, c)
            if (c.momentum) event("momentum_scroll_end", id, JSONObject().put("value", scrollInfo(id, v)))
        }
        v.setOnScrollChangeListener { _, _, _, _, _ ->
            val ae = c.ae
            if (ae != null) {
                val info = scrollInfo(id, v)
                val vals = JSONObject()
                val it = ae.keys()
                while (it.hasNext()) { val key = it.next(); if (info.has(key)) vals.put(ae.getInt(key).toString(), info.getDouble(key)) }
                anim.aset(vals)
            }
            val now = android.os.SystemClock.uptimeMillis()
            if (c.emit && now - c.last >= c.throttle) { c.last = now; emitScroll(id, v, c) }
            ui.removeCallbacks(c.idle!!)
            ui.postDelayed(c.idle!!, 90)
        }
        v.setOnTouchListener { _, e ->
            when (e.actionMasked) {
                android.view.MotionEvent.ACTION_MOVE -> if (!c.dragging) {
                    c.dragging = true
                    if (c.begin) event("scroll_begin_drag", id, JSONObject().put("value", scrollInfo(id, v)))
                }
                android.view.MotionEvent.ACTION_UP, android.view.MotionEvent.ACTION_CANCEL -> if (c.dragging) {
                    c.dragging = false
                    if (c.end) event("scroll_end_drag", id, JSONObject().put("value", scrollInfo(id, v)))
                    ui.removeCallbacks(c.idle!!)
                    ui.postDelayed(c.idle!!, 90)
                }
            }
            false
        }
    }

    private fun scrollTo(id: Int, x: Double?, y: Double?, animated: Boolean) {
        val v = views[id] as? FrameLayout ?: return
        val f = frames[id or CONTENT]
        val horiz = v is PxHScroll
        val tx = x?.let { (it * d).roundToInt() } ?: if (horiz) max(0, ((f?.get(2) ?: 0f) * d).roundToInt() - v.width) else v.scrollX
        val ty = y?.let { (it * d).roundToInt() } ?: if (!horiz) max(0, ((f?.get(3) ?: 0f) * d).roundToInt() - v.height) else v.scrollY
        if (animated) {
            if (horiz) (v as PxHScroll).smoothScrollTo(tx, ty) else (v as PxScroll).smoothScrollTo(tx, ty)
        } else v.scrollTo(tx, ty)
    }

    // -- Image -------------------------------------------------------------------------------------
    private fun applyImage(id: Int, v: ImageView, props: JSONObject, removed: Set<String>) {
        if (props.has("resize_mode") || "resize_mode" in removed) {
            v.scaleType = when (props.optString("resize_mode", "cover")) {
                "contain" -> ImageView.ScaleType.FIT_CENTER
                "stretch" -> ImageView.ScaleType.FIT_XY
                "center" -> ImageView.ScaleType.CENTER
                else -> ImageView.ScaleType.CENTER_CROP
            }
        }
        if (props.has("tint_color") || "tint_color" in removed) {
            val t = props.opt("tint_color")
            val c = when (t) {
                is Number -> t.toInt()
                is String -> try { android.graphics.Color.parseColor(t) } catch (_: Exception) { null }
                else -> null
            }
            if (c != null) v.setColorFilter(c, android.graphics.PorterDuff.Mode.SRC_IN) else v.clearColorFilter()
        }
        if (props.has("source") || "source" in removed) {
            val uri = props.optJSONObject("source")?.optString("uri")
            if (uri.isNullOrEmpty()) {
                imgReq.remove(id); v.setImageDrawable(null); layout.markDirty(id)
            } else if (imgReq[id] != uri) {
                imgReq[id] = uri
                images.load(uri) { bmp, err ->
                    if (imgReq[id] != uri || views[id] !== v) return@load
                    if (bmp != null) {
                        v.setImageBitmap(bmp)
                        layout.markDirty(id)
                        flush()
                        event("load", id, JSONObject().put("value", JSONObject()
                            .put("width", bmp.width / d.toDouble()).put("height", bmp.height / d.toDouble())))
                    } else event("error", id, JSONObject().put("value", JSONObject().put("message", err ?: "error")))
                }
            }
        }
    }

    // -- TextInput ---------------------------------------------------------------------------------
    private val inputCfg = HashMap<Int, JSONObject>()
    private val wired = HashSet<Int>()

    private fun applyInput(id: Int, e: EditText, props: JSONObject, removed: Set<String>) {
        val cfg = inputCfg.getOrPut(id) { JSONObject() }
        var typeDirty = false
        for (k in removed) if (cfg.has(k)) { cfg.remove(k); typeDirty = true }
        val it = props.keys()
        while (it.hasNext()) {
            val k = it.next()
            when (k) {
                "keyboard_type", "secure", "multiline", "auto_capitalize", "auto_correct" -> { cfg.put(k, props.get(k)); typeDirty = true }
                "return_key" -> cfg.put(k, props.get(k)).also { typeDirty = true }
                "max_length" -> e.filters = if (props.optInt(k, 0) > 0) arrayOf(android.text.InputFilter.LengthFilter(props.getInt(k))) else arrayOf()
                "editable" -> { val on = props.optBoolean(k, true); e.isFocusable = on; e.isFocusableInTouchMode = on; e.isCursorVisible = on }
                "placeholder_color" -> try { e.setHintTextColor(android.graphics.Color.parseColor(props.optString(k))) } catch (_: Exception) {}
                "select_on_focus" -> e.setSelectAllOnFocus(props.optBoolean(k))
                "auto_focus" -> if (props.optBoolean(k) && wired.contains(id)) focusLater(e)
            }
        }
        if (typeDirty) {
            val multi = cfg.optBoolean("multiline")
            var t = when (cfg.optString("keyboard_type", "default")) {
                "number" -> android.text.InputType.TYPE_CLASS_NUMBER
                "decimal" -> android.text.InputType.TYPE_CLASS_NUMBER or android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL
                "phone" -> android.text.InputType.TYPE_CLASS_PHONE
                "email" -> android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS
                "url" -> android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_URI
                else -> android.text.InputType.TYPE_CLASS_TEXT
            }
            if ((t and android.text.InputType.TYPE_MASK_CLASS) == android.text.InputType.TYPE_CLASS_TEXT) {
                t = t or when (cfg.optString("auto_capitalize", "none")) {
                    "sentences" -> android.text.InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
                    "words" -> android.text.InputType.TYPE_TEXT_FLAG_CAP_WORDS
                    "characters" -> android.text.InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS
                    else -> 0
                }
                if (multi) t = t or android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE
                if (!cfg.optBoolean("auto_correct", true)) t = t or android.text.InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
                if (cfg.optBoolean("secure")) t = (t and android.text.InputType.TYPE_MASK_FLAGS.inv() and android.text.InputType.TYPE_MASK_VARIATION.inv()) or
                    android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD
            } else if (cfg.optBoolean("secure")) {
                t = t or android.text.InputType.TYPE_NUMBER_VARIATION_PASSWORD
            }
            val keepSel = e.selectionStart
            e.inputType = t
            e.setSingleLine(!multi)
            if (multi) e.gravity = e.gravity or Gravity.TOP
            e.imeOptions = when (cfg.optString("return_key", "done")) {
                "go" -> android.view.inputmethod.EditorInfo.IME_ACTION_GO
                "next" -> android.view.inputmethod.EditorInfo.IME_ACTION_NEXT
                "search" -> android.view.inputmethod.EditorInfo.IME_ACTION_SEARCH
                "send" -> android.view.inputmethod.EditorInfo.IME_ACTION_SEND
                else -> android.view.inputmethod.EditorInfo.IME_ACTION_DONE
            }
            if (keepSel >= 0 && keepSel <= e.text.length) e.setSelection(keepSel)
            layout.markDirty(id)
        }
    }

    private fun focusLater(e: EditText) {
        e.post {
            e.requestFocus()
            (ctx.getSystemService(Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager)
                .showSoftInput(e, 0)
        }
    }

    // -- native modules ----------------------------------------------------------------------------
    private fun reply(id: Int, value: Any?, error: String? = null) {
        val p = JSONObject()
        if (error != null) p.put("error", error) else p.put("value", value ?: JSONObject.NULL)
        event("call_result", id, p)
    }

    private var statusLight: Boolean? = null

    /** Dark glyphs on a light background. Dialogs reset the window appearance, so this is reapplied on focus. */
    fun applyStatusBar() {
        val light = statusLight ?: return
        val act = ctx as? android.app.Activity ?: return
        act.runOnUiThread {
            val w = act.window
            if (Build.VERSION.SDK_INT >= 30) {
                val m = android.view.WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS or
                    android.view.WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS
                w.insetsController?.setSystemBarsAppearance(if (light) m else 0, m)
            } else if (Build.VERSION.SDK_INT >= 23) {
                @Suppress("DEPRECATION") run {
                    var f = w.decorView.systemUiVisibility
                    f = if (light) f or android.view.View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR
                        else f and android.view.View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR.inv()
                    w.decorView.systemUiVisibility = f
                }
            }
        }
    }

    private fun call(id: Int, module: String, method: String, args: JSONArray, wantReply: Boolean) {
        try {
            val out: Any? = when ("$module.$method") {
                "Scroll.to" -> { scrollTo(args.getInt(0), args.getDouble(1), args.getDouble(2), args.optBoolean(3, true)); null }
                "Scroll.to_end" -> { scrollTo(args.getInt(0), null, null, args.optBoolean(1, true)); null }
                "Back.exit" -> { (ctx as? android.app.Activity)?.finish(); null }
                "StatusBar.set_style" -> { statusLight = args.optString(0, "dark") == "dark"; applyStatusBar(); null }
                "Back.set_enabled" -> { backEnabled = args.optBoolean(0, false); null }
                "Keyboard.dismiss" -> {
                    val act = ctx as? android.app.Activity
                    val f = act?.currentFocus
                    if (f != null) {
                        (ctx.getSystemService(Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager)
                            .hideSoftInputFromWindow(f.windowToken, 0)
                        f.clearFocus()
                    }
                    null
                }
                "Clipboard.set_string" -> {
                    (ctx.getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager)
                        .setPrimaryClip(android.content.ClipData.newPlainText("pyxpo", args.optString(0)))
                    null
                }
                "Clipboard.get_string" -> {
                    val c = (ctx.getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager).primaryClip
                    if (c != null && c.itemCount > 0) c.getItemAt(0).coerceToText(ctx).toString() else ""
                }
                "Linking.open_url" -> {
                    ctx.startActivity(android.content.Intent(android.content.Intent.ACTION_VIEW, android.net.Uri.parse(args.optString(0)))
                        .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
                    null
                }
                "Toast.show" -> {
                    android.widget.Toast.makeText(ctx, args.optString(0),
                        if (args.optBoolean(1)) android.widget.Toast.LENGTH_LONG else android.widget.Toast.LENGTH_SHORT).show()
                }
                "Vibration.vibrate" -> {
                    val ms = args.optLong(0, 50)
                    if (Build.VERSION.SDK_INT >= 31) {
                        (ctx.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as android.os.VibratorManager).defaultVibrator
                            .vibrate(android.os.VibrationEffect.createOneShot(ms, android.os.VibrationEffect.DEFAULT_AMPLITUDE))
                    } else {
                        @Suppress("DEPRECATION")
                        (ctx.getSystemService(Context.VIBRATOR_SERVICE) as android.os.Vibrator).vibrate(ms)
                    }
                    null
                }
                "Picker.date" -> {
                    val act = ctx
                    var done = false
                    fun fin(v: Any?) { if (!done) { done = true; if (wantReply) reply(id, v) } }
                    val d = android.app.DatePickerDialog(act, { _, y, m, dd -> fin(JSONArray().put(y).put(m + 1).put(dd)) },
                        args.getInt(0), args.getInt(1) - 1, args.getInt(2))
                    fun ms(a: JSONArray?): Long? = a?.let {
                        java.util.Calendar.getInstance().apply { clear(); set(it.getInt(0), it.getInt(1) - 1, it.getInt(2)) }.timeInMillis
                    }
                    ms(args.optJSONArray(3))?.let { d.datePicker.minDate = it }
                    ms(args.optJSONArray(4))?.let { d.datePicker.maxDate = it }
                    args.optString(5).takeIf { it.isNotEmpty() }?.let { d.setTitle(it) }
                    d.setOnCancelListener { fin(null) }
                    d.show()
                    return
                }
                "Picker.time" -> {
                    var done = false
                    fun fin(v: Any?) { if (!done) { done = true; if (wantReply) reply(id, v) } }
                    val d = android.app.TimePickerDialog(ctx, { _, h, m -> fin(JSONArray().put(h).put(m)) },
                        args.getInt(0), args.getInt(1), args.optBoolean(2, false))
                    args.optString(3).takeIf { it.isNotEmpty() }?.let { d.setTitle(it) }
                    d.setOnCancelListener { fin(null) }
                    d.show()
                    return
                }
                "Picker.choose" -> {
                    val labels = args.getJSONArray(0)
                    val items = Array(labels.length()) { labels.getString(it) }
                    var done = false
                    fun fin(v: Any?) { if (!done) { done = true; if (wantReply) reply(id, v) } }
                    val b = android.app.AlertDialog.Builder(ctx)
                    args.optString(2).takeIf { it.isNotEmpty() }?.let { b.setTitle(it) }
                    b.setSingleChoiceItems(items, args.optInt(1, -1)) { dlg, i -> fin(i); dlg.dismiss() }
                    b.setOnCancelListener { fin(null) }
                    b.show()
                    return
                }
                "Picker.choose_many" -> {
                    val labels = args.getJSONArray(0)
                    val items = Array(labels.length()) { labels.getString(it) }
                    val sel = args.optJSONArray(1) ?: JSONArray()
                    val checked = BooleanArray(items.size) { i -> (0 until sel.length()).any { sel.getInt(it) == i } }
                    var done = false
                    fun fin(v: Any?) { if (!done) { done = true; if (wantReply) reply(id, v) } }
                    val b = android.app.AlertDialog.Builder(ctx)
                    args.optString(2).takeIf { it.isNotEmpty() }?.let { b.setTitle(it) }
                    b.setMultiChoiceItems(items, checked) { _, i, c -> checked[i] = c }
                    b.setPositiveButton(android.R.string.ok) { _, _ ->
                        fin(JSONArray().also { a -> checked.forEachIndexed { i, c -> if (c) a.put(i) } })
                    }
                    b.setNegativeButton(android.R.string.cancel) { _, _ -> fin(null) }
                    b.setOnCancelListener { fin(null) }
                    b.show()
                    return
                }
                "Alert.alert" -> {
                    val labels = args.optJSONArray(2) ?: JSONArray().put("OK")
                    val b = android.app.AlertDialog.Builder(ctx).setTitle(args.optString(0)).setMessage(args.optString(1))
                    var done = false
                    fun fin(i: Int) { if (!done) { done = true; if (wantReply) reply(id, i) } }
                    if (labels.length() > 0) b.setPositiveButton(labels.optString(0)) { _, _ -> fin(0) }
                    if (labels.length() > 1) b.setNegativeButton(labels.optString(1)) { _, _ -> fin(1) }
                    if (labels.length() > 2) b.setNeutralButton(labels.optString(2)) { _, _ -> fin(2) }
                    b.setOnCancelListener { fin(-1) }
                    b.show()
                    return
                }
                else -> { if (wantReply) reply(id, null, "unknown native call $module.$method"); return }
            }
            if (wantReply) reply(id, out)
        } catch (e: Exception) {
            if (wantReply) reply(id, null, e.toString())
        }
    }

    private val a11y = HashMap<Int, JSONObject>()
    private val touching = HashSet<Int>()
    private val pressy = HashSet<Int>()
    private val rawTouch = HashSet<Int>()
    private val touchKeys = HashMap<Int, HashSet<String>>()  // live on_press*/on_touch_* props per view
    private val closeListeners = HashSet<Int>()

    private fun merge(dst: JSONObject, props: JSONObject, removed: Set<String>) {
        for (k in removed) dst.remove(k)
        val it = props.keys()
        while (it.hasNext()) { val k = it.next(); if (k.startsWith("accessib")) dst.put(k, props.get(k)) }
    }

    private fun applyA11y(v: View, a: JSONObject) {
        val st = a.optJSONObject("accessibility_state")
        val parts = ArrayList<String>()
        a.optString("accessibility_label", "").takeIf { it.isNotEmpty() }?.let { v.contentDescription = it }
        if (!a.has("accessibility_label")) v.contentDescription = null
        if (st != null) {
            if (st.has("checked")) parts.add(if (st.optBoolean("checked")) "checked" else "not checked")
            if (st.optBoolean("selected")) parts.add("selected")
            if (st.optBoolean("disabled")) parts.add("disabled")
        }
        a.optString("accessibility_value", "").takeIf { it.isNotEmpty() }?.let { parts.add(it) }
        if (android.os.Build.VERSION.SDK_INT >= 30) v.stateDescription = if (parts.isEmpty()) null else parts.joinToString(", ")
        if (a.has("accessible")) v.importantForAccessibility =
            if (a.optBoolean("accessible")) View.IMPORTANT_FOR_ACCESSIBILITY_YES else View.IMPORTANT_FOR_ACCESSIBILITY_NO
        val role = a.optString("accessibility_role", "")
        val hint = a.optString("accessibility_hint", "")
        v.accessibilityDelegate = object : View.AccessibilityDelegate() {
            override fun onInitializeAccessibilityNodeInfo(h: View, info: android.view.accessibility.AccessibilityNodeInfo) {
                super.onInitializeAccessibilityNodeInfo(h, info)
                when (role) {
                    "button", "link", "imagebutton" -> info.className = "android.widget.Button"
                    "switch" -> info.className = "android.widget.Switch"
                    "checkbox" -> info.className = "android.widget.CheckBox"
                    "radio" -> info.className = "android.widget.RadioButton"
                    "image" -> info.className = "android.widget.ImageView"
                    "header" -> info.isHeading = true
                }
                if (st != null && st.has("checked")) { info.isCheckable = true; info.isChecked = st.optBoolean("checked") }
                if (st != null && st.optBoolean("disabled")) info.isEnabled = false
                if (hint.isNotEmpty() && android.os.Build.VERSION.SDK_INT >= 26) info.hintText = hint
            }
        }
    }

    /** Touch tracking for any view with on_press* handlers: press_in, press_out, press (release inside), long_press. */
    @android.annotation.SuppressLint("ClickableViewAccessibility")
    private fun attachTouch(id: Int, v: View) {
        if (!touching.add(id)) return
        val handler = android.os.Handler(android.os.Looper.getMainLooper())
        var down = false
        var long = false
        val longRun = Runnable { if (down) { long = true; event("long_press", id) } }
        val dens = ctx.resources.displayMetrics.density
        fun raw(name: String, e: android.view.MotionEvent) {
            if (!rawTouch.contains(id)) return
            event(name, id, JSONObject().put("value", JSONObject().put("x", e.x / dens).put("y", e.y / dens)
                .put("page_x", e.rawX / dens).put("page_y", e.rawY / dens)))
        }
        v.setOnTouchListener { view, e ->
            // Handlers were removed later (e.g. a disabled Slider): stop consuming touches.
            if (!pressy.contains(id) && !rawTouch.contains(id)) { down = false; handler.removeCallbacks(longRun); return@setOnTouchListener false }
            val inside = e.x >= -24 && e.y >= -24 && e.x <= view.width + 24 && e.y <= view.height + 24
            when (e.actionMasked) {
                android.view.MotionEvent.ACTION_DOWN -> {
                    down = true; long = false
                    view.parent?.requestDisallowInterceptTouchEvent(rawTouch.contains(id))
                    raw("touch_start", e)
                    if (pressy.contains(id)) handler.postDelayed(longRun, 500)
                    if (pressy.contains(id)) event("press_in", id, JSONObject().put("x", e.x / ctx.resources.displayMetrics.density)
                        .put("y", e.y / ctx.resources.displayMetrics.density))
                    true
                }
                android.view.MotionEvent.ACTION_MOVE -> {
                    raw("touch_move", e)
                    if (down && !inside) { down = false; handler.removeCallbacks(longRun); if (pressy.contains(id)) event("press_out", id) }
                    true
                }
                android.view.MotionEvent.ACTION_UP -> {
                    handler.removeCallbacks(longRun)
                    raw("touch_end", e)
                    if (down && pressy.contains(id)) { event("press_out", id); if (!long) event("press", id) }
                    down = false
                    true
                }
                android.view.MotionEvent.ACTION_CANCEL -> {
                    handler.removeCallbacks(longRun)
                    raw("touch_end", e)
                    if (down && pressy.contains(id)) event("press_out", id)
                    down = false
                    true
                }
                else -> false
            }
        }
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
        val italic = s.optString("font_style") == "italic"
        val file = s.optString("font_file")
        val fam = s.optString("font_family")
        return typefaces.getOrPut("$file|$fam|$w|$italic") {
            val weight = when (w) { "bold" -> 700; "normal" -> 400; else -> w.toIntOrNull() ?: 400 }
            val base: Typeface = when {
                file.isNotEmpty() -> fontCache.getOrPut(file) {
                    try { Typeface.createFromFile(file) } catch (e: Exception) { null }
                } ?: Typeface.DEFAULT
                fam == "monospace" || fam == "serif" || fam == "sans-serif" -> Typeface.create(fam, Typeface.NORMAL)
                else -> Typeface.DEFAULT
            }
            if (Build.VERSION.SDK_INT >= 28) Typeface.create(base, weight, italic)
            else Typeface.create(base, (if (weight >= 600) 1 else 0) or (if (italic) 2 else 0))
        }
    }

    private val typefaces = HashMap<String, Typeface>()

    /** Modals live on the root so they cover the whole screen whatever their Python parent is. */
    private fun host(id: Int, parent: Int) = if (types[id] == "Modal") 1 else parent

    /** Android back: the topmost Modal consumes it and gets `request_close` if it listens (as in RN). */
    fun handleBack(): Boolean {
        val root = groupOf(1) ?: return false
        for (i in root.childCount - 1 downTo 0) {
            val id = views.entries.firstOrNull { it.value === root.getChildAt(i) }?.key ?: continue
            if (types[id] == "Modal") { if (closeListeners.contains(id)) event("request_close", id); return true }
        }
        if (backEnabled) { event("hardware_back", 0); return true }  // Python navigators consume it
        return false
    }

    /** Set by the Python `Back` module while a navigator has something to pop (a Stack past its root, an open Drawer). */
    private var backEnabled = false

    private fun insert(parent0: Int, id: Int, index0: Int) {
        val parent = host(id, parent0)
        val index = if (parent != parent0) Int.MAX_VALUE else index0
        val g = groupOf(parent) ?: return
        val v = views[id] ?: return
        (v.parent as? ViewGroup)?.removeView(v)
        g.addView(v, min(index, g.childCount), ViewGroup.LayoutParams(-2, -2))
        layout.remove(parentNode(parent), id)
        layout.insert(parentNode(parent), id, index)
        if (g is PxNav && v.parent === g) g.pushed(v)
        if (types[id] == "Modal") v.bringToFront()
    }

    private fun remove(parent0: Int, id: Int) {
        val parent = host(id, parent0)
        val v = views[id] ?: return
        val g = groupOf(parent)
        if (!(g is PxNav && g.popped(v))) g?.removeView(v)
        layout.remove(parentNode(parent), id)
    }

    private fun delete(id: Int) {
        val v = views.remove(id)
        binds.remove(id)
        touching.remove(id); pressy.remove(id); rawTouch.remove(id); touchKeys.remove(id); closeListeners.remove(id); a11y.remove(id); inputCfg.remove(id); wired.remove(id)
        texts.remove(id); spans.remove(id)
        val host = v?.parent as? ViewGroup
        if (!(host is PxNav && v in host.lingering)) host?.removeView(v)  // a popping screen leaves when its animation ends
        scrolls.remove(id)?.idle?.let { ui.removeCallbacks(it) }  // no stale scroll events for a deleted id
        layoutListeners.remove(id); imgReq.remove(id)
        if (types.remove(id) == "ScrollView") layout.delete(id or CONTENT)
        controls.drop(id)
        layout.delete(id)
        styles.remove(id); frames.remove(id); pads.remove(id); painted.remove(id); defaultText.remove(id)
    }

    private fun parentNode(parent: Int) = if (types[parent] == "ScrollView") parent or CONTENT else parent

    private fun groupOf(parent: Int): ViewGroup? {
        val p = views[parent] ?: return null
        return if (p is PxScrollable) (p as FrameLayout).getChildAt(0) as ViewGroup else p as? ViewGroup
    }

    // -- style -------------------------------------------------------------------------------------
    private fun prop(name: String): Int = propIds.getOrPut(name) { layout.propId(name) }

    private fun animVal(k: String, node: Int): Any {
        val x = anim.resolve(node)
        return if (k == "color" || k.endsWith("_color")) x.toLong() else x
    }

    /** Replaces `{"$a": node}` bindings with the node's current value and records the bindings for the frame loop. */
    private fun resolveBinds(id: Int, s: JSONObject): JSONObject {
        var b: HashMap<String, Int>? = null
        val it = s.keys()
        while (it.hasNext()) {
            val k = it.next()
            val o = s.opt(k)
            if (o is JSONObject && o.has("\$a")) { if (b == null) b = HashMap(); b[k] = o.getInt("\$a") }
        }
        if (b == null) { binds.remove(id); return s }
        val out = JSONObject()
        val ks = s.keys()
        while (ks.hasNext()) { val k = ks.next(); out.put(k, s.get(k)) }
        for ((k, n) in b) out.put(k, animVal(k, n))
        binds[id] = b
        return out
    }

    private fun depsOf(node: Int): Set<Int> = depCache.getOrPut(node) { anim.deps(node) }

    private val TRANSFORM = setOf("opacity", "rotate", "scale", "scale_x", "scale_y", "translate_x", "translate_y")

    /** Per-frame: write the changed animated values straight onto views. Layout keys re-run the engine once. */
    private fun onAnimFrame(touched: Set<Int>) {
        var relayout = false
        for ((id, b) in binds) {
            val v = views[id] ?: continue
            val s = styles[id] ?: continue
            var tr = false; var box = false; var txt = false; var shadow = false
            for ((k, n) in b) {
                if (touched.none { it in depsOf(n) }) continue
                val nv = animVal(k, n)
                s.put(k, nv)
                when {
                    k in TRANSFORM -> tr = true
                    k == "color" -> txt = true
                    k.startsWith("shadow") || k == "elevation" -> shadow = true
                    else -> {
                        if (prop(k) >= 0) { pushLayout(id, k, nv); layout.markDirty(id); relayout = true }
                        if (k.startsWith("background") || k.startsWith("border")) box = true
                    }
                }
            }
            if (tr) paintTransform(v, s)
            if (box) paintBox(id, v, s)
            if (shadow) paintShadow(v, s)
            if (txt && v is TextView) v.setTextColor(col(s, "color"))
        }
        if (relayout) flush()
    }

    private fun applyStyle(id: Int, v: View, raw: JSONObject) {
        val s = resolveBinds(id, raw)
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
        v.visibility = if (s.optString("display") == "none") View.GONE else View.VISIBLE
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
        paintShadow(v, s)
        paintTransform(v, s)
        if (v is TextView) paintText(id, v, s)
    }

    private fun paintTransform(v: View, s: JSONObject) {
        v.alpha = num(s, "opacity", 1.0).toFloat().coerceIn(0f, 1f)
        v.rotation = num(s, "rotate").toFloat()
        v.scaleX = (num(s, "scale", 1.0) * num(s, "scale_x", 1.0)).toFloat()
        v.scaleY = (num(s, "scale", 1.0) * num(s, "scale_y", 1.0)).toFloat()
        v.translationX = px(num(s, "translate_x"))
        v.translationY = px(num(s, "translate_y"))
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
            val spec = BoxSpec(if (s.has("background_color")) col(s, "background_color") else null,
                grad?.optDouble("angle", 180.0)?.toFloat() ?: 0f, colors, stops, radii, bw, bc)
            if ((v.background as? BoxDrawable)?.spec?.sameAs(spec) != true) v.background = BoxDrawable(spec)
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
        val mw = (max(0, v.measuredWidth - p[0] - p[2]) + (if (v is android.widget.TextView) 1 else 0)) / d  // +1px: frame rounding must not clip the last glyph
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

    private var insets = IntArray(4)  // px: left, top, right, bottom
    private var kbPx = 0

    /** System bar / cutout insets and keyboard height (px) from the activity. */
    fun setInsets(l: Int, t: Int, r: Int, b: Int, kb: Int) {
        insets = intArrayOf(l, t, r, b); kbPx = kb
        sendEnv()
    }

    /** Sends the current window/scale/color scheme to Python when it changed. */
    fun sendEnv() {
        if (rootW <= 0) return
        val j = envJson(ctx, rootW, rootH, insets, kbPx)
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
            val c = (views[base] as? FrameLayout)?.getChildAt(0) as? PxGroup ?: return
            val nw = (f[2] * d).roundToInt(); val nh = (f[3] * d).roundToInt()
            if (nw != c.fw || nh != c.fh) { c.fw = nw; c.fh = nh; c.requestLayout() }
            frames[id] = f
            touched.add(base)
            return
        }
        val v = views[id] ?: return
        val old = frames[id]
        frames[id] = f
        if (id in layoutListeners && (old == null || !old.contentEquals(f))) {
            event("layout", id, JSONObject().put("value", JSONObject().put("x", f[0].toDouble()).put("y", f[1].toDouble())
                .put("width", f[2].toDouble()).put("height", f[3].toDouble())))
        }
        if (v is PxScrollable) touched.add(id) else placeView(v, f)
    }

    private fun placeView(v: View, f: FloatArray) {
        val l = (f[0] * d).roundToInt(); val t = (f[1] * d).roundToInt()
        val r = ((f[0] + f[2]) * d).roundToInt(); val b = ((f[1] + f[3]) * d).roundToInt()
        v.measure(MeasureSpec.makeMeasureSpec(r - l, MeasureSpec.EXACTLY), MeasureSpec.makeMeasureSpec(b - t, MeasureSpec.EXACTLY))
        v.layout(l, t, r, b)
    }
}
