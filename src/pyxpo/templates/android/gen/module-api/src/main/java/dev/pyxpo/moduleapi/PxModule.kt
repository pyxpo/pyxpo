package dev.pyxpo.moduleapi

import android.app.Activity
import android.content.Intent
import org.json.JSONArray

/** Completes one call. Safe from any thread; the host hops to the main thread. `value` is JSON-compatible (Map, List, String, Number, Boolean, null). */
typealias PxReply = (value: Any?, error: String?) -> Unit

/** What the app gives a native module. */
interface PxModuleContext {
    val activity: Activity

    /** Starts `intent` and calls `onResult` once. If the activity is recreated meanwhile, `onResult` gets `Activity.RESULT_CANCELED`. */
    fun startForResult(intent: Intent, onResult: (resultCode: Int, data: Intent?) -> Unit)

    /** Asks for runtime permissions; `onResult` maps each permission to granted. Already granted ones are not asked again. */
    fun requestPermissions(permissions: Array<String>, onResult: (Map<String, Boolean>) -> Unit)

    /** Sends a `module` event to Python (`pyxpo.modules.on_event(name, payload)`). Safe from any thread. */
    fun emit(name: String, payload: Map<String, Any?>)
}

/**
 * A native module. `name` is the bridge module name Python calls (for example "ImagePicker").
 * `call` runs on the main thread: do heavy work elsewhere and finish with `reply`.
 * Throw or reply with an error string to fail the call; an unreplied call hangs its Python await.
 */
abstract class PxModule {
    abstract val name: String
    abstract fun call(ctx: PxModuleContext, method: String, args: JSONArray, reply: PxReply)
}
