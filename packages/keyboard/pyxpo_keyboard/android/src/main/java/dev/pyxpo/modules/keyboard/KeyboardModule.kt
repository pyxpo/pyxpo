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
 * and the options [KeyboardService] reads.
 */
class KeyboardModule : PxModule() {
    override val name = "Keyboard"

    override fun call(ctx: PxModuleContext, method: String, args: JSONArray, reply: PxReply) {
        val a = ctx.activity
        when (method) {
            "status" -> reply(status(a), null)
            "openSettings" -> {
                a.startActivity(Intent(Settings.ACTION_INPUT_METHOD_SETTINGS))
                reply(null, null)
            }
            "showPicker" -> {
                (a.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager).showInputMethodPicker()
                reply(null, null)
            }
            "getOptions" -> reply(Options.read(a), null)
            "setOptions" -> {
                val o = args.optJSONObject(0) ?: return reply(null, "set_options needs a dict")
                val values = HashMap<String, Any?>()
                for (k in o.keys()) values[k] = o.opt(k).takeIf { it != JSONObject.NULL }
                val unknown = Options.write(a, values)
                if (unknown.isNotEmpty()) reply(null, "unknown or non-boolean keyboard options: ${unknown.joinToString()}")
                else reply(Options.read(a), null)
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
        return mapOf("supported" to true, "enabled" to enabled, "selected" to selected, "id" to me.flattenToShortString())
    }
}
