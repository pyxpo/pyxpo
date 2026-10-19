package dev.pyxpo.modules.keyboard

import android.content.Context
import android.content.res.Configuration
import android.graphics.drawable.GradientDrawable
import android.icu.text.BreakIterator
import android.inputmethodservice.InputMethodService
import android.media.AudioManager
import android.os.Build
import android.os.SystemClock
import android.text.InputType
import android.util.TypedValue
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsets
import android.view.inputmethod.EditorInfo
import android.widget.BaseAdapter
import android.widget.FrameLayout
import android.widget.GridView
import android.widget.LinearLayout
import android.widget.TextView
import dev.pyxpo.moduleapi.PxProcess

/** Keyboard options the app sets (`pyxpo_keyboard.set_options`) and the service reads on every field. */
object Options {
    private const val FILE = "pyxpo_keyboard"
    val DEFAULTS = mapOf<String, Any>(
        "number_row" to false, "haptics" to true, "sound" to false,
        "auto_capitalize" to true, "double_space_period" to true,
    )

    fun read(context: Context): Map<String, Any> {
        val p = context.getSharedPreferences(FILE, Context.MODE_PRIVATE)
        return DEFAULTS.mapValues { (k, d) -> if (d is Boolean) p.getBoolean(k, d) else d }
    }

    /** Writes the known boolean options in `values`; returns the names it did not know. */
    fun write(context: Context, values: Map<String, Any?>): List<String> {
        val e = context.getSharedPreferences(FILE, Context.MODE_PRIVATE).edit()
        val unknown = ArrayList<String>()
        for ((k, v) in values) {
            if (DEFAULTS[k] is Boolean && v is Boolean) e.putBoolean(k, v) else unknown.add(k)
        }
        e.apply()
        return unknown
    }
}

/** What a field is and how the keyboard treats it. */
class FieldInfo(info: EditorInfo) {
    private val cls = info.inputType and InputType.TYPE_MASK_CLASS
    private val variation = info.inputType and InputType.TYPE_MASK_VARIATION

    /** Passwords, PINs and incognito fields: no AI, no voice, nothing sent or kept. */
    val sensitive = (cls == InputType.TYPE_CLASS_TEXT && variation in PASSWORDS) ||
        (cls == InputType.TYPE_CLASS_NUMBER && variation == InputType.TYPE_NUMBER_VARIATION_PASSWORD) ||
        (info.imeOptions and EditorInfo.IME_FLAG_NO_PERSONALIZED_LEARNING) != 0

    val page = when (cls) {
        InputType.TYPE_CLASS_NUMBER, InputType.TYPE_CLASS_DATETIME -> Page.NUMBERS
        InputType.TYPE_CLASS_PHONE -> Page.PHONE
        else -> Page.LETTERS
    }

    val field = when (variation) {
        InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS, InputType.TYPE_TEXT_VARIATION_WEB_EMAIL_ADDRESS -> Field.EMAIL
        InputType.TYPE_TEXT_VARIATION_URI -> Field.URL
        else -> Field.TEXT
    }.takeIf { cls == InputType.TYPE_CLASS_TEXT } ?: Field.TEXT

    val multiline = cls == InputType.TYPE_CLASS_TEXT && (info.inputType and InputType.TYPE_TEXT_FLAG_MULTI_LINE) != 0

    /** For the app (`get_field_async`): text, email, url, number, phone or datetime. */
    val kind = when (cls) {
        InputType.TYPE_CLASS_NUMBER -> "number"
        InputType.TYPE_CLASS_PHONE -> "phone"
        InputType.TYPE_CLASS_DATETIME -> "datetime"
        else -> field.name.lowercase()
    }

    /** The editor action enter performs, or null when enter types a new line. */
    val action: Int? = run {
        val a = info.imeOptions and EditorInfo.IME_MASK_ACTION
        when {
            (info.imeOptions and EditorInfo.IME_FLAG_NO_ENTER_ACTION) != 0 -> null
            a == EditorInfo.IME_ACTION_NONE || a == EditorInfo.IME_ACTION_UNSPECIFIED -> null
            multiline && a == EditorInfo.IME_ACTION_DONE -> null
            else -> a
        }
    }

    val actionLabel: String? = when (action) {
        EditorInfo.IME_ACTION_GO -> "Go"
        EditorInfo.IME_ACTION_SEARCH -> "Search"
        EditorInfo.IME_ACTION_SEND -> "Send"
        EditorInfo.IME_ACTION_NEXT -> "Next"
        EditorInfo.IME_ACTION_DONE -> "Done"
        EditorInfo.IME_ACTION_PREVIOUS -> "Prev"
        else -> null
    }

    companion object {
        private val PASSWORDS = setOf(
            InputType.TYPE_TEXT_VARIATION_PASSWORD,
            InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD,
            InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD,
        )
    }
}

/**
 * The system keyboard: a toolbar strip over the key grid (or the emoji panel). Everything a key does runs here,
 * on the main thread, without Python. The app's toolbar buttons (`set_toolbar_async`) start Python headless and
 * send it `Keyboard.toolbar`; Python answers through [KeyboardModule] (status line, text to commit).
 */
class KeyboardService : InputMethodService(), KeyboardView.Listener {
    companion object {
        /** The keyboard while it exists, for [KeyboardModule]. Main thread. */
        var current: KeyboardService? = null
            private set
        const val TOOLBAR = "Keyboard.toolbar"
        const val INPUT = "Keyboard.input"
    }

    private lateinit var keys: KeyboardView
    private lateinit var emoji: View
    private lateinit var status: TextView
    private lateinit var bar: LinearLayout
    private lateinit var tools: LinearLayout
    private var appStatus = ""
    private var palette = Palette(false)
    private var navInset = 0
    private var night = false

    private var page = Page.LETTERS
    private var shift = Shift.OFF
    private var lastShift = 0L
    private var lastSpace = 0L
    private var field: FieldInfo? = null
    private var options = Options.DEFAULTS

    private val dp get() = resources.displayMetrics.density

    override fun onCreate() {
        super.onCreate()
        current = this
    }

    override fun onDestroy() {
        if (current === this) current = null
        super.onDestroy()
    }

    override fun onCreateInputView(): View {
        night = isNight(resources.configuration)
        palette = Palette(night)
        keys = KeyboardView(this, this)
        emoji = emojiPanel()
        emoji.visibility = View.GONE
        bar = toolbar()
        val body = FrameLayout(this).apply {
            addView(keys, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
            addView(emoji, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        }
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(palette.background)
            addView(bar, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, (40 * dp).toInt()))
            addView(body, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        }
        // edge-to-edge windows (Android 15+) draw under the navigation bar: keep the keys above it. A theme or
        // font-size change rebuilds this view inside the same window, whose insets did not change, so nothing
        // dispatches them again: the rebuilt view starts with the last inset (asking for them anew changes the
        // window height while it shows, and the app's keyboard animation can then leave it hidden).
        root.setPadding(0, 0, 0, navInset)
        root.setOnApplyWindowInsetsListener { v, insets ->
            val bottom = if (Build.VERSION.SDK_INT >= 30) insets.getInsets(WindowInsets.Type.navigationBars()).bottom
                         else @Suppress("DEPRECATION") insets.systemWindowInsetBottom
            navInset = bottom
            v.setPadding(0, 0, 0, bottom)
            insets
        }
        keys.palette = palette
        return root
    }

    private fun isNight(c: Configuration) = (c.uiMode and Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES

    // The method's xml marks uiMode as handled (Android 14+), so a light/dark switch does not reset the window:
    // after that reset the keys stayed invisible (the window's surface kept alpha 0) until the field was left.
    // Swap in keys drawn in the new colours instead.
    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        if (!::keys.isInitialized || isNight(newConfig) == night) return
        setInputView(onCreateInputView())
        val info = currentInputEditorInfo
        if (info != null && isInputViewShown) onStartInputView(info, true)
    }

    // The default hides the keys while a hardware keyboard is attached (the emulator, a Bluetooth keyboard); the
    // keys also carry the toolbar and, later, voice, so they stay available like Gboard's.
    override fun onEvaluateInputViewShown(): Boolean {
        super.onEvaluateInputViewShown()
        return true
    }

    override fun onStartInputView(info: EditorInfo, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        options = Options.read(this)
        val f = FieldInfo(info)
        field = f
        if (!restarting) page = f.page
        showEmoji(false)
        appStatus = ""
        showStatus("")
        refreshToolbar()
        // Python answers the toolbar: warm it up while the user looks at the field (not in private fields)
        if (!f.sensitive && Toolbar.read(this).isNotEmpty()) PxProcess.start(this)
        PxProcess.emit(INPUT, mapOf("state" to "start", "field" to fieldKind(f)))
        keys.enterLabel = f.actionLabel
        keys.spaceLabel = "English"
        relayout()
        shift = Shift.OFF
        autoShift()
    }

    override fun onFinishInputView(finishingInput: Boolean) {
        super.onFinishInputView(finishingInput)
        shift = Shift.OFF
        PxProcess.emit(INPUT, mapOf("state" to "finish"))
    }

    override fun onUpdateSelection(oldSelStart: Int, oldSelEnd: Int, newSelStart: Int, newSelEnd: Int,
                                   candidatesStart: Int, candidatesEnd: Int) {
        super.onUpdateSelection(oldSelStart, oldSelEnd, newSelStart, newSelEnd, candidatesStart, candidatesEnd)
        autoShift()
    }

    private fun relayout() {
        val globe = Build.VERSION.SDK_INT >= 28 && shouldOfferSwitchingToNextInputMethod()
        keys.rows = Layouts.rows(page, globe, options["number_row"] == true, field?.field ?: Field.TEXT)
        keys.shift = shift
    }

    /** One-shot shift at the start of a sentence, when the field asks for capitals. */
    private fun autoShift() {
        if (shift == Shift.LOCK || page != Page.LETTERS) return
        val info = currentInputEditorInfo ?: return
        val caps = options["auto_capitalize"] == true &&
            (currentInputConnection?.getCursorCapsMode(info.inputType) ?: 0) != 0
        setShift(if (caps) Shift.ONCE else Shift.OFF)
    }

    private fun setShift(s: Shift) {
        shift = s
        if (::keys.isInitialized) keys.shift = s
    }

    private fun feedback() {
        if (options["haptics"] == true) keys.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
        if (options["sound"] == true) (getSystemService(Context.AUDIO_SERVICE) as AudioManager)
            .playSoundEffect(AudioManager.FX_KEYPRESS_STANDARD, -1f)
    }

    // -- keys

    override fun onKey(key: Key) {
        feedback()
        when (key.code) {
            Codes.SHIFT -> {
                val now = SystemClock.uptimeMillis()
                setShift(when {
                    shift == Shift.LOCK -> Shift.OFF
                    now - lastShift < 350 -> Shift.LOCK     // double tap
                    shift == Shift.ONCE -> Shift.OFF
                    else -> Shift.ONCE
                })
                lastShift = now
            }
            Codes.DELETE -> delete()
            Codes.ENTER -> enter()
            Codes.SPACE -> space()
            Codes.SYMBOLS -> { page = Page.SYMBOLS; relayout() }
            Codes.MORE -> { page = Page.MORE; relayout() }
            Codes.LETTERS -> { page = Page.LETTERS; relayout(); autoShift() }
            Codes.EMOJI -> showEmoji(true)
            Codes.GLOBE -> if (Build.VERSION.SDK_INT >= 28) switchToNextInputMethod(false)
            else -> type(if (shift != Shift.OFF && key.text.length == 1) key.text.uppercase() else key.text)
        }
    }

    override fun onHold(key: Key): Boolean {
        when (key.code) {
            Codes.SPACE -> {
                (getSystemService(Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager)
                    .showInputMethodPicker()
                return true
            }
            Codes.SHIFT -> { setShift(Shift.LOCK); return true }
        }
        val alt = key.alt?.takeIf { it.isNotBlank() } ?: return false
        feedback()
        type(alt)
        return true
    }

    override fun onRepeat(key: Key) {
        if (key.code == Codes.DELETE) delete()
    }

    private fun type(text: String) {
        val ic = currentInputConnection ?: return
        ic.commitText(text, 1)
        if (shift == Shift.ONCE) setShift(Shift.OFF)
        // an apostrophe from the symbol page ends the detour, as on other keyboards ("don't")
        if (page == Page.SYMBOLS && text == "'") { page = Page.LETTERS; relayout() }
    }

    private fun space() {
        val ic = currentInputConnection ?: return
        val now = SystemClock.uptimeMillis()
        val before = ic.getTextBeforeCursor(2, 0)?.toString() ?: ""
        if (options["double_space_period"] == true && now - lastSpace < 600 && before.length == 2 &&
            before[1] == ' ' && before[0].isLetterOrDigit()) {
            ic.deleteSurroundingText(1, 0)
            ic.commitText(". ", 1)
            lastSpace = 0
        } else {
            ic.commitText(" ", 1)
            lastSpace = now
        }
        if (page != Page.LETTERS && page != Page.NUMBERS && page != Page.PHONE) { page = Page.LETTERS; relayout() }
    }

    private fun delete() {
        val ic = currentInputConnection ?: return
        val selected = ic.getSelectedText(0)
        if (!selected.isNullOrEmpty()) ic.commitText("", 1)
        else sendDownUpKeyEvents(KeyEvent.KEYCODE_DEL)  // the editor removes a whole emoji or surrogate pair
    }

    private fun enter() {
        val ic = currentInputConnection ?: return
        val action = field?.action
        if (action != null) ic.performEditorAction(action) else sendKeyChar('\n')
    }

    // -- the app's side (KeyboardModule calls these on the main thread)

    private fun fieldKind(f: FieldInfo) = mapOf("kind" to f.kind, "action" to f.actionLabel,
                                               "private" to f.sensitive, "multiline" to f.multiline)

    /** The field the keys type in, or null while the keyboard is hidden. Never its text. */
    fun fieldState(): Map<String, Any?>? {
        val f = field ?: return null
        if (!isInputViewShown) return null
        return fieldKind(f) + mapOf("app" to currentInputEditorInfo?.packageName)
    }

    /** Null when `text` went in, else why not. */
    fun commit(text: String): String? {
        val f = field ?: return "no field is focused"
        if (f.sensitive) return "this is a private field: the keyboard does not type app text into it"
        val ic = currentInputConnection ?: return "no field is focused"
        if (text.isNotEmpty()) ic.commitText(text, 1)
        if (shift == Shift.ONCE) setShift(Shift.OFF)
        autoShift()
        return null
    }

    /** The field's text around the cursor, or why it cannot be read (private fields never are). */
    fun text(before: Int, after: Int): Pair<Map<String, Any?>?, String?> {
        val f = field ?: return null to "no field is focused"
        if (f.sensitive) return null to "this is a private field: its text stays in the keyboard"
        val ic = currentInputConnection ?: return null to "no field is focused"
        val b = before.coerceIn(0, 10000)
        val a = after.coerceIn(0, 10000)
        return mapOf("before" to (ic.getTextBeforeCursor(b, 0)?.toString() ?: ""),
                     "selected" to (ic.getSelectedText(0)?.toString() ?: ""),
                     "after" to (ic.getTextAfterCursor(a, 0)?.toString() ?: "")) to null
    }

    /** The app's status line text; the private-field notice wins. */
    fun showStatus(text: String) {
        appStatus = text
        if (!::status.isInitialized) return
        status.text = if (field?.sensitive == true) "🔒  Private field: AI and voice are off" else appStatus
    }

    fun refreshToolbar() {
        if (!::tools.isInitialized) return
        tools.removeAllViews()
        if (field?.sensitive == true) return
        for (b in Toolbar.read(this)) {
            tools.addView(TextView(this).apply {
                text = b.label
                setTextColor(if (b.active) palette.onAccent else palette.text)
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)
                gravity = Gravity.CENTER
                contentDescription = b.description.ifEmpty { b.label }
                if (b.active) background = GradientDrawable().apply { cornerRadius = 16 * dp; setColor(palette.accent) }
                setOnClickListener { feedback(); tapped(b.id) }
            }, LinearLayout.LayoutParams((44 * dp).toInt(), (34 * dp).toInt()).apply {
                gravity = Gravity.CENTER_VERTICAL; marginEnd = (4 * dp).toInt()
            })
        }
    }

    private fun tapped(id: String) {
        val f = field ?: return
        if (f.sensitive) return
        PxProcess.start(this)
        PxProcess.emit(TOOLBAR, mapOf("id" to id, "field" to fieldKind(f)))
    }

    // -- toolbar and emoji panel

    private fun toolbar(): LinearLayout {
        status = TextView(this).apply {
            setTextColor(palette.muted)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            gravity = Gravity.CENTER_VERTICAL
            setPadding((12 * dp).toInt(), 0, (12 * dp).toInt(), 0)
            maxLines = 1
        }
        val app = TextView(this).apply {
            text = "⚙"
            setTextColor(palette.text)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)
            gravity = Gravity.CENTER
            contentDescription = "Open the keyboard app"
            setOnClickListener { openApp() }
        }
        tools = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setBackgroundColor(palette.background)
            addView(status, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f))
            addView(tools, LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.MATCH_PARENT))
            addView(app, LinearLayout.LayoutParams((48 * dp).toInt(), ViewGroup.LayoutParams.MATCH_PARENT))
        }
    }

    private fun openApp() {
        val i = packageManager.getLaunchIntentForPackage(packageName) ?: return
        requestHideSelf(0)     // the keys would stay over the app (and seem to do nothing when it is open already)
        i.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
        startActivity(i)
    }

    private fun showEmoji(on: Boolean) {
        if (!::keys.isInitialized) return
        // The body wraps its content, so the scrolling panel takes exactly the keys' height (else the whole screen).
        if (on && keys.height > 0) emoji.layoutParams = emoji.layoutParams.apply { height = keys.height }
        emoji.visibility = if (on) View.VISIBLE else View.GONE
        keys.visibility = if (on) View.INVISIBLE else View.VISIBLE   // keeps the keyboard's height
    }

    private fun emojiPanel(): View {
        val list = ArrayList<String>()
        val it = BreakIterator.getCharacterInstance()
        it.setText(Layouts.EMOJI)
        var start = it.first()
        var end = it.next()
        while (end != BreakIterator.DONE) { list.add(Layouts.EMOJI.substring(start, end)); start = end; end = it.next() }

        val grid = GridView(this).apply {
            numColumns = GridView.AUTO_FIT
            columnWidth = (44 * dp).toInt()
            stretchMode = GridView.STRETCH_COLUMN_WIDTH
            adapter = object : BaseAdapter() {
                override fun getCount() = list.size
                override fun getItem(position: Int) = list[position]
                override fun getItemId(position: Int) = position.toLong()
                override fun getView(position: Int, convertView: View?, parent: ViewGroup?): View {
                    val v = (convertView as? TextView) ?: TextView(this@KeyboardService).apply {
                        gravity = Gravity.CENTER
                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 26f)
                        layoutParams = ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, (48 * dp).toInt())
                    }
                    v.text = list[position]
                    return v
                }
            }
            setOnItemClickListener { _, _, position, _ -> feedback(); currentInputConnection?.commitText(list[position], 1) }
        }
        fun button(text: String, onTap: () -> Unit) = TextView(this).apply {
            this.text = text
            setTextColor(palette.text)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
            gravity = Gravity.CENTER
            background = GradientDrawable().apply { cornerRadius = 7 * dp; setColor(palette.special) }
            setOnClickListener { feedback(); onTap() }
        }
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding((6 * dp).toInt(), (4 * dp).toInt(), (6 * dp).toInt(), (6 * dp).toInt())
            val lp = { w: Float -> LinearLayout.LayoutParams(0, (44 * dp).toInt(), w).apply { marginStart = (3 * dp).toInt(); marginEnd = (3 * dp).toInt() } }
            addView(button("ABC") { showEmoji(false) }, lp(1.5f))
            addView(View(this@KeyboardService), lp(5f))
            addView(button("⌫") { delete() }, lp(1.5f))
        }
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(palette.background)
            addView(grid, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
            addView(row, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        }
    }
}
