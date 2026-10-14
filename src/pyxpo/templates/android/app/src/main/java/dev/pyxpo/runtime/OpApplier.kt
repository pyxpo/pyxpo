package dev.pyxpo.runtime

import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.text.Editable
import android.text.TextWatcher
import android.util.TypedValue
import android.view.View
import android.view.ViewGroup
import android.widget.*
import org.json.JSONArray
import org.json.JSONObject

/** Applies JSON op batches on the UI thread. Keeps id -> View. Root id is 1. */
class OpApplier(
    private val ctx: Context,
    private val container: ViewGroup,
    private val sendEvent: (String) -> Unit,
) {
    private val views = HashMap<Int, View>()
    private val types = HashMap<Int, String>()
    private val suppress = HashSet<View>()
    private val density = ctx.resources.displayMetrics.density
    private fun dp(v: Double) = (v * density).toInt()

    init {
        // Root id 1 is implicit in the ops protocol: it is never created by the reconciler.
        val root = PyxpoLayout(ctx)
        root.fixedW = -1
        container.addView(root, ViewGroup.LayoutParams(-1, -1))
        views[1] = root
        types[1] = "Root"
    }

    fun apply(batch: String) {
        val ops = JSONArray(batch)
        for (i in 0 until ops.length()) {
            val o = ops.getJSONObject(i)
            when (o.getString("op")) {
                "create" -> create(o.getInt("id"), o.getString("type"), o.optJSONObject("props") ?: JSONObject())
                "update" -> update(o.getInt("id"), o.optJSONObject("props") ?: JSONObject(), o.optJSONArray("removed"))
                "insert" -> insert(o.getInt("parent"), o.getInt("id"), o.getInt("index"))
                "remove" -> remove(o.getInt("parent"), o.getInt("id"))
                "delete" -> { views.remove(o.getInt("id")); types.remove(o.getInt("id")) }
            }
        }
    }

    private fun event(name: String, id: Int, payload: JSONObject = JSONObject()) {
        sendEvent(JSONObject().put("event", name).put("id", id).put("payload", payload).toString())
    }

    private fun create(id: Int, type: String, props: JSONObject) {
        val v: View = when (type) {
            "Text" -> TextView(ctx)
            "Button" -> Button(ctx).also { it.setOnClickListener { event("press", id) } }
            "Image" -> ImageView(ctx)
            "TextInput" -> EditText(ctx)
            "ScrollView" -> ScrollView(ctx).also { it.addView(PyxpoLayout(ctx)) }
            else -> PyxpoLayout(ctx)
        }
        views[id] = v
        types[id] = type
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
        if ("style" in r) applyStyle(v, JSONObject())
        val keys = props.keys()
        while (keys.hasNext()) {
            val k = keys.next()
            when (k) {
                "text" -> if (v is TextView && v !is EditText) v.text = props.optString(k)
                          else if (v is Button) v.text = props.optString(k)
                "value" -> (v as? EditText)?.let {
                    if (it.text.toString() != props.optString(k)) {
                        suppress.add(it); it.setText(props.optString(k)); it.setSelection(it.text.length)
                        suppress.remove(it)
                    }
                }
                "placeholder" -> (v as? EditText)?.hint = props.optString(k)
                "style" -> applyStyle(v, props.optJSONObject(k) ?: JSONObject())
            }
        }
    }

    private fun applyStyle(v: View, s: JSONObject) {
        val target = if (v is ScrollView) v.getChildAt(0) else v
        if (target is PyxpoLayout) {
            target.row = s.optString("flex_direction", "column") == "row"
            target.gap = dp(s.optDouble("gap", 0.0))
            target.alignItems = s.optString("align_items", "stretch")
            target.justify = s.optString("justify_content", "start")
            if (target === v) {
                target.fixedW = if (s.has("width")) dp(s.getDouble("width")) else -1
                target.fixedH = if (s.has("height")) dp(s.getDouble("height")) else -1
                target.flexGrow = s.optDouble("flex", 0.0).toFloat()
                target.margin = dp(s.optDouble("margin", 0.0))
            }
        } else {
            v.tag = PyxpoLayout.Extra(s.optDouble("flex", 0.0).toFloat(), dp(s.optDouble("margin", 0.0)))
        }
        val p = dp(s.optDouble("padding", 0.0))
        target.setPadding(p, p, p, p)
        if (s.has("background_color")) v.setBackgroundColor(parseColor(s.getString("background_color")))
        if (v is TextView) {
            if (s.has("color")) v.setTextColor(parseColor(s.getString("color")))
            v.setTextSize(TypedValue.COMPLEX_UNIT_SP, s.optDouble("font_size", 14.0).toFloat())
            if (s.optString("font_weight") == "bold") v.setTypeface(null, Typeface.BOLD)
        }
        v.requestLayout()
    }

    private fun parseColor(c: String): Int = try { Color.parseColor(c) } catch (e: Exception) { Color.TRANSPARENT }

    private fun childParent(parent: Int): ViewGroup? {
        val p = views[parent] ?: return null
        return if (p is ScrollView) p.getChildAt(0) as ViewGroup else p as? ViewGroup
    }

    private fun insert(parent: Int, id: Int, index: Int) {
        val g = childParent(parent) ?: return
        val v = views[id] ?: return
        (v.parent as? ViewGroup)?.removeView(v)
        g.addView(v, minOf(index, g.childCount), ViewGroup.LayoutParams(-2, -2))
    }

    private fun remove(parent: Int, id: Int) {
        val v = views[id] ?: return
        childParent(parent)?.removeView(v)
    }

}
