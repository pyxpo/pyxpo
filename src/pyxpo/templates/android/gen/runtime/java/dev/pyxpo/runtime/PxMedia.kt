package dev.pyxpo.runtime

import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import java.util.concurrent.Executors

class PxMediaError(message: String) : Exception(message)

/**
 * Native side of pyxpo's media APIs (ImageTools, ImagePicker, MediaLibrary, Share). `OpApplier` hands unknown
 * native calls here. Heavy work runs on one single-thread executor; replies always go back on the main thread.
 */
object PxMedia {
    private val executor = Executors.newSingleThreadExecutor { r -> Thread(r, "pyxpo-media") }
    private val main = Handler(Looper.getMainLooper())

    /** Returns false when `module.method` is not a media call. */
    fun handle(ctx: Context, module: String, method: String, args: org.json.JSONArray, reply: (Any?, String?) -> Unit): Boolean {
        when ("$module.$method") {
            "ImageTools.ping" -> background(reply) { "pong" }
            else -> return false
        }
        return true
    }

    /** Runs `work` on the media executor and replies on main with its value, or its error message. */
    fun background(reply: (Any?, String?) -> Unit, work: () -> Any?) {
        executor.execute {
            var value: Any? = null
            var message: String? = null
            try { value = work() }
            catch (e: PxMediaError) { message = e.message }
            catch (e: Throwable) { message = e.toString() }
            main.post { reply(value, message) }
        }
    }

    /** Forwarded from `MainActivity.onActivityResult` (photo picker, ...). Returns true when consumed. */
    fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?): Boolean = false
}
