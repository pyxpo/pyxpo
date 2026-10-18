package dev.pyxpo.runtime

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Outline
import android.view.View
import android.view.ViewOutlineProvider
import android.widget.CheckBox
import android.widget.ProgressBar
import android.widget.RadioButton
import android.widget.SeekBar
import android.widget.Switch
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.roundToInt

/**
 * Platform controls (Switch, CheckBox, RadioButton, SeekBar, ProgressBar) as pyxpo host views.
 * Defaults are the system look; props only override colors, so the native feel stays unless asked otherwise.
 */
class PxControls(private val ctx: Context, private val emit: (String, Int, JSONObject) -> Unit) {
    companion object {
        val TYPES = setOf("NativeSwitch", "NativeCheckBox", "NativeRadio", "NativeSlider", "NativeProgress", "NativeSpinner")
        private const val RES = 10000
        private val CHECKED = intArrayOf(android.R.attr.state_checked)
        private val ANY = intArrayOf()
    }

    private val cfg = HashMap<Int, JSONObject>()
    private val quiet = HashSet<View>()

    fun drop(id: Int) { cfg.remove(id) }

    fun create(id: Int, type: String): View = when (type) {
        "NativeSwitch" -> Switch(ctx).also { s ->
            s.setOnCheckedChangeListener { b, c -> if (b !in quiet) emit("value_change", id, JSONObject().put("value", c)) }
        }
        "NativeCheckBox" -> CheckBox(ctx).also { s ->
            s.setOnCheckedChangeListener { b, c -> if (b !in quiet) emit("value_change", id, JSONObject().put("value", c)) }
        }
        "NativeRadio" -> RadioButton(ctx).also { it.isClickable = false; it.isFocusable = false }
        "NativeSlider" -> SeekBar(ctx).also { s ->
            s.max = RES
            // A split track is clipped around the thumb's bounds; on some images that clip swallows the whole track
            // and only the thumb reaches the screen. The thumb is drawn over the track anyway.
            s.splitTrack = false
            s.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                override fun onProgressChanged(b: SeekBar, p: Int, fromUser: Boolean) {
                    if (fromUser) emit("value_change", id, JSONObject().put("value", valueOf(id, b)))
                }
                override fun onStartTrackingTouch(b: SeekBar) { b.parent?.requestDisallowInterceptTouchEvent(true) }
                override fun onStopTrackingTouch(b: SeekBar) {
                    emit("sliding_complete", id, JSONObject().put("value", valueOf(id, b)))
                }
            })
        }
        "NativeProgress" -> ProgressBar(ctx, null, android.R.attr.progressBarStyleHorizontal).also { p ->
            p.max = RES
            p.clipToOutline = true
            p.outlineProvider = object : ViewOutlineProvider() {
                override fun getOutline(v: View, o: Outline) { o.setRoundRect(0, 0, v.width, v.height, v.height / 2f) }
            }
        }
        else -> ProgressBar(ctx).also { it.isIndeterminate = true }
    }

    private fun min(id: Int) = cfg[id]?.optDouble("minimum", 0.0) ?: 0.0
    private fun max(id: Int) = cfg[id]?.optDouble("maximum", 1.0) ?: 1.0

    private fun valueOf(id: Int, b: SeekBar): Double {
        val lo = min(id); val hi = max(id)
        var v = lo + b.progress.toDouble() / RES * (hi - lo)
        val step = cfg[id]?.optDouble("step", 0.0) ?: 0.0
        if (step > 0) v = lo + Math.round((v - lo) / step) * step
        return v.coerceIn(lo, hi)
    }

    private fun color(c: JSONObject, k: String): Int? = if (c.has(k) && !c.isNull(k)) c.optLong(k).toInt() else null

    private fun states(on: Int?, off: Int?, fallbackOff: Int): ColorStateList? =
        if (on == null && off == null) null
        else ColorStateList(arrayOf(CHECKED, ANY), intArrayOf(on ?: off!!, off ?: fallbackOff))

    private fun tint(v: View, c: JSONObject) {
        when (v) {
            is Switch -> {
                v.trackTintList = states(color(c, "track_on"), color(c, "track_off"), 0xFFBDBDBD.toInt())
                v.thumbTintList = states(color(c, "thumb_on"), color(c, "thumb_off"), 0xFFFAFAFA.toInt())
            }
            is CheckBox, is RadioButton -> {
                val on = color(c, "color"); val off = color(c, "unchecked_color")
                (v as android.widget.CompoundButton).buttonTintList = states(on, off, 0xFF757575.toInt())
            }
            is SeekBar -> {
                color(c, "min_track_color")?.let { v.progressTintList = ColorStateList.valueOf(it) }
                color(c, "max_track_color")?.let { v.progressBackgroundTintList = ColorStateList.valueOf(it) }
                color(c, "thumb_color")?.let { v.thumbTintList = ColorStateList.valueOf(it) }
            }
            is ProgressBar -> {
                val col = color(c, "color"); val track = color(c, "track_color")
                if (col != null) {
                    v.progressTintList = ColorStateList.valueOf(col)
                    v.indeterminateTintList = ColorStateList.valueOf(col)
                }
                if (track != null) v.progressBackgroundTintList = ColorStateList.valueOf(track)
            }
        }
    }

    /** Merges `props` into the control's config and applies it. `removed` props reset to the system default. */
    fun update(id: Int, v: View, props: JSONObject, removed: Set<String>) {
        val c = cfg.getOrPut(id) { JSONObject() }
        for (k in removed) c.remove(k)
        val ks = props.keys()
        while (ks.hasNext()) { val k = ks.next(); c.put(k, props.get(k)) }
        if (props.has("disabled") || "disabled" in removed) v.isEnabled = !c.optBoolean("disabled", false)
        when (v) {
            is android.widget.CompoundButton -> if (c.has("value")) {
                val on = c.optBoolean("value")
                if (v.isChecked != on) { quiet.add(v); v.isChecked = on; quiet.remove(v) }
            }
            is SeekBar -> {
                val lo = min(id); val hi = max(id)
                val p = if (hi > lo) (((c.optDouble("value", lo) - lo) / (hi - lo)).coerceIn(0.0, 1.0) * RES).roundToInt() else 0
                if (v.progress != p && !v.isPressed) v.progress = p
            }
            is ProgressBar -> {
                if (v.max == RES) {
                    v.isIndeterminate = c.optBoolean("indeterminate", false)
                    if (!v.isIndeterminate) v.progress = (c.optDouble("value", 0.0) * RES).roundToInt()
                } else if (c.has("animating")) {
                    v.visibility = if (c.optBoolean("animating", true)) View.VISIBLE else View.INVISIBLE
                }
            }
        }
        tint(v, c)
    }
}
