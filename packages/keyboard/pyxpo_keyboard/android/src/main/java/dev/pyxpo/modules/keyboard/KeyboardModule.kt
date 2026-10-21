package dev.pyxpo.modules.keyboard

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.provider.Settings
import android.view.inputmethod.InputMethodManager
import dev.pyxpo.moduleapi.PxModule
import dev.pyxpo.moduleapi.PxModuleContext
import dev.pyxpo.moduleapi.PxReply
import org.json.JSONArray
import org.json.JSONObject

/**
 * The app side of the keyboard: whether the user turned it on and picked it, the system screens to do that,
 * the options [KeyboardService] reads, and (while the keyboard shows) its toolbar, status line and the field.
 * Works headless too: the keyboard starts Python with `PxProcess.start` when a toolbar button is tapped.
 */
class KeyboardModule : PxModule() {
    override val name = "Keyboard"

    override fun call(ctx: PxModuleContext, method: String, args: JSONArray, reply: PxReply) {
        val c = ctx.context
        when (method) {
            "status" -> reply(status(c), null)
            "openSettings" -> {
                c.startActivity(Intent(Settings.ACTION_INPUT_METHOD_SETTINGS).apply {
                    if (!ctx.hasActivity) addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                })
                reply(null, null)
            }
            "showPicker" -> {
                (c.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager).showInputMethodPicker()
                reply(null, null)
            }
            "getOptions" -> reply(Options.read(c), null)
            "setOptions" -> {
                val o = args.optJSONObject(0) ?: return reply(null, "set_options needs a dict")
                val values = HashMap<String, Any?>()
                for (k in o.keys()) values[k] = o.opt(k).takeIf { it != JSONObject.NULL }
                val unknown = Options.write(c, values)
                if (unknown.isNotEmpty()) reply(null, "unknown or non-boolean keyboard options: ${unknown.joinToString()}")
                else reply(Options.read(c), null)
            }
            "setToolbar" -> {
                val list = args.optJSONArray(0) ?: return reply(null, "set_toolbar needs a list of buttons")
                Toolbar.write(c, list)
                KeyboardService.current?.refreshToolbar()
                reply(null, null)
            }
            "setStatus" -> {
                KeyboardService.current?.showStatus(args.optString(0, ""))
                reply(null, null)
            }
            "showPanel" -> {
                val s = KeyboardService.current ?: return reply(null, "the keyboard is not showing")
                val spec = args.optJSONObject(0) ?: return reply(null, "show_panel needs a dict")
                reply(null, s.showPanel(spec))
            }
            "hidePanel" -> {
                KeyboardService.current?.hidePanel()
                reply(null, null)
            }
            "setPanelLevel" -> {
                KeyboardService.current?.setPanelLevel(args.optDouble(0, 0.0).toFloat())
                reply(null, null)
            }
            "field" -> reply(KeyboardService.current?.fieldState(), null)
            "commitText" -> {
                val s = KeyboardService.current ?: return reply(null, "the keyboard is not showing")
                reply(null, s.commit(args.optString(0, "")))
            }
            "getText" -> {
                val s = KeyboardService.current ?: return reply(null, "the keyboard is not showing")
                val o = args.optJSONObject(0) ?: JSONObject()
                val (text, err) = s.text(o.optInt("before", 1000), o.optInt("after", 1000))
                reply(text, err)
            }
            else -> reply(null, "unknown native call Keyboard.$method")
        }
    }

    private fun status(context: Context): Map<String, Any?> {
        val me = ComponentName(context, KeyboardService::class.java)
        val imm = context.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        val enabled = imm.enabledInputMethodList.any { it.component == me }
        val current = Settings.Secure.getString(context.contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD)
        val selected = current != null && ComponentName.unflattenFromString(current) == me
        return mapOf("supported" to true, "enabled" to enabled, "selected" to selected, "id" to me.flattenToShortString(),
                     "showing" to (KeyboardService.current?.fieldState() != null))
    }
}

/** Toolbar buttons the app sets (`set_toolbar_async`), kept so the keyboard shows them before Python runs. */
object Toolbar {
    private const val FILE = "pyxpo_keyboard"
    private const val KEY = "toolbar"

    class Button(val id: String, val label: String, val description: String, val active: Boolean, val icon: String = "")

    fun read(context: Context): List<Button> {
        val raw = context.getSharedPreferences(FILE, Context.MODE_PRIVATE).getString(KEY, null) ?: return emptyList()
        val list = try { JSONArray(raw) } catch (e: Exception) { return emptyList() }
        return (0 until list.length()).mapNotNull { i ->
            val o = list.optJSONObject(i) ?: return@mapNotNull null
            Button(o.optString("id"), o.optString("label"), o.optString("description"), o.optBoolean("active"), o.optString("icon"))
                .takeIf { it.id.isNotEmpty() && it.label.isNotEmpty() }
        }
    }

    fun write(context: Context, list: JSONArray) {
        context.getSharedPreferences(FILE, Context.MODE_PRIVATE).edit().putString(KEY, list.toString()).apply()
    }
}
