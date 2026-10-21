package dev.pyxpo.modules.video

import dev.pyxpo.moduleapi.PxModule
import dev.pyxpo.moduleapi.PxModuleContext
import dev.pyxpo.moduleapi.PxNativeView
import dev.pyxpo.moduleapi.PxReply
import org.json.JSONArray

/** pyxpo-video on Android: a view (`PxVideoView`) that plays a file or URL with `android.widget.VideoView`. */
class VideoModule : PxModule() {
    override val name = "Video"
    override val viewTypes = setOf("PxVideoView")

    override fun makeView(ctx: PxModuleContext, type: String, emit: (name: String, value: Any?) -> Unit): PxNativeView =
        PxVideo(ctx.activity, emit)

    override fun call(ctx: PxModuleContext, method: String, args: JSONArray, reply: PxReply) {
        ctx.activity.runOnUiThread {
            val v = (if (args.length() > 0) ctx.view(args.optInt(0, -1)) else null) as? PxVideo
            if (v == null) {
                reply(null, "The VideoView is not mounted")
                return@runOnUiThread
            }
            when (method) {
                "play" -> { v.play(); reply(null, null) }
                "pause" -> { v.pause(); reply(null, null) }
                "seek" -> { v.seek(args.optDouble(1, 0.0)); reply(null, null) }
                else -> reply(null, "Video has no method $method")
            }
        }
    }
}
