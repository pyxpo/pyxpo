package dev.pyxpo.moduleapi

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.view.View
import org.json.JSONArray
import org.json.JSONObject

/** Completes one call. Safe from any thread; the host hops to the main thread. `value` is JSON-compatible (Map, List, String, Number, Boolean, null). */
typealias PxReply = (value: Any?, error: String?) -> Unit

/** What the app gives a native module. */
interface PxModuleContext {
    /** The activity on screen. Throws while the app runs headless (see [PxProcess]): check [hasActivity] first. */
    val activity: Activity

    /** The app context. Always there, also while the app runs headless. */
    val context: Context get() = activity

    /** False while Python runs with no activity (a Service started it with [PxProcess.start]). [activity],
     *  [startForResult] and [requestPermissions] throw then. */
    val hasActivity: Boolean get() = true

    /** Starts `intent` and calls `onResult` once. If the activity is recreated meanwhile, `onResult` gets `Activity.RESULT_CANCELED`. */
    fun startForResult(intent: Intent, onResult: (resultCode: Int, data: Intent?) -> Unit)

    /** Asks for runtime permissions; `onResult` maps each permission to granted. Already granted ones are not asked again. */
    fun requestPermissions(permissions: Array<String>, onResult: (Map<String, Boolean>) -> Unit)

    /** Sends a `module` event to Python (`pyxpo.modules.on_event(name, payload)`). Safe from any thread. */
    fun emit(name: String, payload: Map<String, Any?>)

    /** The mounted native view with this tag (the Python handle's node id), if a module made it. */
    fun view(tag: Int): PxNativeView?
}

/**
 * Python for code that runs without the app's activity, like a Service (an input method, a background job).
 * [start] boots Python headless when it does not run yet: the app module runs as usual, native module calls
 * work with no activity ([PxModuleContext.hasActivity] is false), and the first activity that opens mounts the
 * app's screens. Main thread.
 */
object PxProcess {
    /** Set by the app runtime when it is made. Posts to the main thread itself. */
    @Volatile var sink: ((name: String, payload: Map<String, Any?>) -> Unit)? = null

    /** Starts Python if it does not run yet. */
    fun start(context: Context) {
        Class.forName("dev.pyxpo.runtime.PyxpoRuntime").getMethod("startHeadless", Context::class.java)
            .invoke(null, context.applicationContext)
    }

    /** Sends a `module` event to Python, like [PxModuleContext.emit]. Events sent before Python is ready wait for it.
     *  False when the runtime was not made yet: call [start] first. Safe from any thread. */
    fun emit(name: String, payload: Map<String, Any?>): Boolean {
        val s = sink ?: return false
        s(name, payload)
        return true
    }
}

/**
 * A view a module provides (`pyxpo.module_api.native_view`). Made, updated and disposed on the main thread.
 * The layout engine sizes it from its style, like a plain View; it has no children.
 */
interface PxNativeView {
    val view: View

    /** Changed props (`on_<event>` props are `true` while Python listens) and removed prop names. The first call has every initial prop. */
    fun update(props: JSONObject, removed: Set<String>)

    /** The view left the tree for good. */
    fun dispose() {}
}

/**
 * A native module. `name` is the bridge module name Python calls (for example "ImagePicker").
 * `call` runs on the main thread: do heavy work elsewhere and finish with `reply`.
 * Throw or reply with an error string to fail the call; an unreplied call hangs its Python await.
 */
abstract class PxModule {
    abstract val name: String
    abstract fun call(ctx: PxModuleContext, method: String, args: JSONArray, reply: PxReply)

    /** JSON-compatible values Python reads synchronously (`pyxpo.module_api.constants`). Built once at startup, on main. */
    open fun constants(context: Context): Map<String, Any?> = emptyMap()

    /** Native view types this module provides. */
    open val viewTypes: Set<String> = emptySet()

    /** Makes a view of one of [viewTypes]. `emit(name, value)` calls the view's `on_<name>` prop in Python (main thread). */
    open fun makeView(ctx: PxModuleContext, type: String, emit: (name: String, value: Any?) -> Unit): PxNativeView =
        throw UnsupportedOperationException("$name has no view type $type")

    /** The running activity got a new intent (already its `intent`), for example a notification tap. Main thread. */
    open fun onNewIntent(ctx: PxModuleContext, intent: Intent) {}
}
