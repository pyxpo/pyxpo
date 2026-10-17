package dev.pyxpo.modules.audio

import android.app.Activity
import android.app.Application
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.os.Bundle
import dev.pyxpo.moduleapi.PxModule
import dev.pyxpo.moduleapi.PxModuleContext
import dev.pyxpo.moduleapi.PxReply
import org.json.JSONArray
import org.json.JSONObject

/**
 * pyxpo-audio on Android: one MediaPlayer per player id Python gives. Files and URLs prepare asynchronously; a
 * play asked for before that starts once ready. Sound pauses while the activity is paused and plays on after.
 */
class AudioModule : PxModule() {
    override val name = "Audio"

    private class Player(val mp: MediaPlayer) {
        var prepared = false
        var wantsPlay = false
        var seekTo = -1
    }

    private val players = HashMap<Int, Player>()
    private var lifecycle: Application.ActivityLifecycleCallbacks? = null

    override fun call(ctx: PxModuleContext, method: String, args: JSONArray, reply: PxReply) {
        ctx.activity.runOnUiThread {
            try {
                run(ctx, method, args)
                reply(null, null)
            } catch (e: Exception) {
                reply(null, e.message ?: e.toString())
            }
        }
    }

    private fun run(ctx: PxModuleContext, method: String, args: JSONArray) {
        val id = args.getInt(0)
        val p = players[id]
        when (method) {
            "create" -> {
                watch(ctx.activity)
                players.remove(id)?.mp?.release()
                players[id] = make(args.getString(1), args.optBoolean(2), args.optDouble(3, 1.0).toFloat())
            }
            "play" -> p?.let {
                it.wantsPlay = true
                if (it.prepared) it.mp.start()
            }
            "pause" -> p?.let {
                it.wantsPlay = false
                if (it.prepared && it.mp.isPlaying) it.mp.pause()
            }
            "seek" -> p?.let {
                val ms = (args.getDouble(1) * 1000).toInt()
                if (it.prepared) it.mp.seekTo(ms) else it.seekTo = ms
            }
            "set" -> p?.let {
                val o = args.optJSONObject(1) ?: JSONObject()
                if (o.has("loop")) it.mp.isLooping = o.getBoolean("loop")
                if (o.has("volume")) o.getDouble("volume").toFloat().let { v -> it.mp.setVolume(v, v) }
            }
            "release" -> players.remove(id)?.mp?.release()
            else -> throw IllegalArgumentException("unknown native call Audio.$method")
        }
    }

    private fun make(src: String, loop: Boolean, volume: Float): Player {
        val mp = MediaPlayer()
        val p = Player(mp)
        mp.setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
            .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build())
        mp.setDataSource(if (src.startsWith("file://")) android.net.Uri.parse(src).path ?: src else src)
        mp.isLooping = loop
        mp.setVolume(volume, volume)
        mp.setOnPreparedListener {
            p.prepared = true
            if (p.seekTo >= 0) mp.seekTo(p.seekTo)
            if (p.wantsPlay) mp.start()
        }
        mp.setOnErrorListener { _, what, extra ->
            android.util.Log.w("pyxpo-audio", "cannot play $src ($what, $extra)")
            true
        }
        mp.prepareAsync()
        return p
    }

    private fun watch(activity: Activity) {
        if (lifecycle != null) return
        val cb = object : Application.ActivityLifecycleCallbacks {
            override fun onActivityPaused(a: Activity) {
                if (a === activity) players.values.forEach { if (it.prepared && it.mp.isPlaying) it.mp.pause() }
            }
            override fun onActivityResumed(a: Activity) {
                if (a === activity) players.values.forEach { if (it.prepared && it.wantsPlay) it.mp.start() }
            }
            override fun onActivityDestroyed(a: Activity) {
                if (a !== activity) return
                players.values.forEach { it.mp.release() }
                players.clear()
                a.application.unregisterActivityLifecycleCallbacks(this)
                lifecycle = null
            }
            override fun onActivityCreated(a: Activity, b: Bundle?) {}
            override fun onActivityStarted(a: Activity) {}
            override fun onActivityStopped(a: Activity) {}
            override fun onActivitySaveInstanceState(a: Activity, b: Bundle) {}
        }
        activity.application.registerActivityLifecycleCallbacks(cb)
        lifecycle = cb
    }
}
