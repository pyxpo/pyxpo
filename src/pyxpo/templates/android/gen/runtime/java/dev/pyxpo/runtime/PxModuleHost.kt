package dev.pyxpo.runtime

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Handler
import android.os.Looper
import android.util.SparseArray
import dev.pyxpo.moduleapi.PxModule
import dev.pyxpo.moduleapi.PxModuleContext
import dev.pyxpo.moduleapi.PxNativeView
import dev.pyxpo.moduleapi.PxReply
import org.json.JSONArray
import org.json.JSONObject

/**
 * Routes `Module.method` calls to the native modules linked into this app (`PxModuleRegistry`). Main thread only.
 * `act` is null for the headless host [PyxpoRuntime] uses while no activity is on screen.
 */
class PxModuleHost(override val context: Context, private val act: Activity?,
                   private val emitEvent: (String, JSONObject) -> Unit) : PxModuleContext {
    override val activity: Activity
        get() = act ?: throw IllegalStateException("no activity: the app runs headless (a service started Python); open the app for this call")

    override val hasActivity: Boolean get() = act != null

    private val main = Handler(Looper.getMainLooper())
    private val modules: Map<String, PxModule> = allModules.associateBy { it.name }
    private val results = SparseArray<(Int, Intent?) -> Unit>()
    private val permissionCallbacks = SparseArray<(Map<String, Boolean>) -> Unit>()
    private var nextCode = 0

    val names: List<String> get() = modules.keys.sorted()

    private val views = HashMap<Int, PxNativeView>()

    /** Makes a module view, or returns null when no linked module provides `type`. */
    fun makeView(type: String, tag: Int, emit: (String, Any?) -> Unit): PxNativeView? {
        val m = modules.values.firstOrNull { type in it.viewTypes } ?: return null
        return m.makeView(this, type, emit).also { views[tag] = it }
    }

    fun dropView(tag: Int) { views.remove(tag)?.dispose() }

    override fun view(tag: Int): PxNativeView? = views[tag]

    /** Returns false when no linked module has this name. */
    fun call(module: String, method: String, args: JSONArray, reply: PxReply): Boolean {
        val m = modules[module] ?: return false
        var done = false
        val once: PxReply = { v, e ->
            main.post { if (!done) { done = true; reply(v?.let { JSONObject.wrap(it) }, e) } }
        }
        try { m.call(this, method, args, once) }
        catch (e: Throwable) { once(null, e.message ?: e.toString()) }
        return true
    }

    override fun startForResult(intent: Intent, onResult: (Int, Intent?) -> Unit) {
        val code = allocate { results.indexOfKey(it) >= 0 }
        results.put(code, onResult)
        try { activity.startActivityForResult(intent, code) }
        catch (e: Throwable) { results.remove(code); throw e }
    }

    override fun requestPermissions(permissions: Array<String>, onResult: (Map<String, Boolean>) -> Unit) {
        val missing = permissions.filter { context.checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
        if (missing.isEmpty()) { onResult(permissions.associateWith { true }); return }
        val code = allocate { permissionCallbacks.indexOfKey(it) >= 0 }
        // Report every requested permission, not just the ones the dialog asked about.
        permissionCallbacks.put(code, { asked: Map<String, Boolean> -> onResult(permissions.associateWith { asked[it] ?: (it !in missing) }) })
        activity.requestPermissions(missing.toTypedArray(), code)
    }

    override fun emit(name: String, payload: Map<String, Any?>) {
        val data = JSONObject.wrap(payload) as? JSONObject ?: JSONObject()
        main.post { emitEvent(name, data) }
    }

    /** Request codes 0x5000..0x5FFF, skipping ones still waiting. */
    private fun allocate(taken: (Int) -> Boolean): Int {
        repeat(0x1000) {
            val c = 0x5000 + (nextCode++ and 0xFFF)
            if (!taken(c)) return c
        }
        throw IllegalStateException("too many pending native requests")
    }

    fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?): Boolean {
        val cb = results.get(requestCode) ?: return false
        results.remove(requestCode)
        cb(resultCode, data)
        return true
    }

    fun onRequestPermissionsResult(requestCode: Int, perms: Array<out String>, grants: IntArray): Boolean {
        val cb = permissionCallbacks.get(requestCode) ?: return false
        permissionCallbacks.remove(requestCode)
        val map = HashMap<String, Boolean>()
        perms.forEachIndexed { i, p -> map[p] = grants.getOrNull(i) == PackageManager.PERMISSION_GRANTED }
        cb(map)
        return true
    }

    fun onNewIntent(intent: Intent) {
        for (m in modules.values) {
            try { m.onNewIntent(this, intent) } catch (e: Throwable) { android.util.Log.e("pyxpo", "${m.name}.onNewIntent", e) }
        }
    }

    /** The activity is going away: pending callbacks can never fire, so cancel them rather than hang Python. */
    fun cancelPending() {
        val r = ArrayList<(Int, Intent?) -> Unit>()
        for (i in 0 until results.size()) r.add(results.valueAt(i))
        results.clear()
        val p = ArrayList<(Map<String, Boolean>) -> Unit>()
        for (i in 0 until permissionCallbacks.size()) p.add(permissionCallbacks.valueAt(i))
        permissionCallbacks.clear()
        r.forEach { it(Activity.RESULT_CANCELED, null) }
        p.forEach { it(emptyMap()) }
    }
}
