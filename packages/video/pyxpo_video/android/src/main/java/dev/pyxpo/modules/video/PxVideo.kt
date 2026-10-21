package dev.pyxpo.modules.video

import android.content.Context
import android.graphics.Color
import android.media.MediaPlayer
import android.net.Uri
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.MediaController
import android.widget.VideoView
import dev.pyxpo.moduleapi.PxNativeView
import org.json.JSONObject
import java.io.File

/** A black box with a centered VideoView, which keeps the video's aspect ratio inside it. */
class PxVideo(private val context: Context, private val emit: (String, Any?) -> Unit) : PxNativeView {
    private val box = FrameLayout(context)
    private val video = VideoView(context)
    private var player: MediaPlayer? = null
    private var source: String? = null
    private var playing = true
    private var loop = false
    private var muted = false
    override val view: View get() = box

    init {
        box.setBackgroundColor(Color.BLACK)
        box.addView(video, FrameLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT,
            ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.CENTER))
        video.setOnPreparedListener { mp ->
            player = mp
            mp.isLooping = loop
            applyMute()
            emit("load", mapOf("duration" to mp.duration / 1000.0, "width" to mp.videoWidth.toDouble(),
                "height" to mp.videoHeight.toDouble()))
            if (playing) video.start()
        }
        video.setOnCompletionListener { if (!loop) emit("end", null) }
        video.setOnErrorListener { _, what, extra ->
            emit("error", mapOf("message" to "cannot play the video (error $what, $extra)"))
            true
        }
    }

    override fun update(props: JSONObject, removed: Set<String>) {
        if (props.has("loop")) { loop = props.getBoolean("loop"); player?.isLooping = loop }
        if (props.has("muted")) { muted = props.getBoolean("muted"); applyMute() }
        if (props.has("controls")) setControls(props.getBoolean("controls"))
        if (props.has("source")) {
            val s = if (props.isNull("source")) null else props.getString("source")
            if (s != source) { source = s; load() }
        }
        if (props.has("playing")) {
            playing = props.getBoolean("playing")
            if (playing) play() else pause()
        }
    }

    fun play() { if (source != null) video.start() }

    fun pause() { if (video.canPause()) video.pause() }

    fun seek(seconds: Double) { video.seekTo((seconds * 1000).toInt()) }

    private fun load() {
        player = null
        val s = source
        if (s == null) { video.stopPlayback(); return }
        video.setVideoURI(if (s.contains("://")) Uri.parse(s) else Uri.fromFile(File(s)))
    }

    private fun setControls(on: Boolean) {
        if (on) {
            val c = MediaController(context)
            c.setAnchorView(video)
            video.setMediaController(c)
        } else {
            video.setMediaController(null)
        }
    }

    private fun applyMute() {
        val v = if (muted) 0f else 1f
        try { player?.setVolume(v, v) } catch (_: IllegalStateException) {}
    }

    override fun dispose() { video.stopPlayback() }
}
