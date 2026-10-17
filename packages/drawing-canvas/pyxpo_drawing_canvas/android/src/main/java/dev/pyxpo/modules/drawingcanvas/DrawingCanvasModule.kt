package dev.pyxpo.modules.drawingcanvas

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import dev.pyxpo.moduleapi.PxModule
import dev.pyxpo.moduleapi.PxModuleContext
import dev.pyxpo.moduleapi.PxNativeView
import dev.pyxpo.moduleapi.PxReply
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID
import kotlin.concurrent.thread
import kotlin.math.roundToInt

/** pyxpo-drawing-canvas on Android: a `Canvas` view (`PxDrawingCanvas`) with undo, redo and image export. */
class DrawingCanvasModule : PxModule() {
    override val name = "DrawingCanvas"
    override val viewTypes = setOf("PxDrawingCanvas")

    override fun makeView(ctx: PxModuleContext, type: String, emit: (name: String, value: Any?) -> Unit): PxNativeView =
        DrawingCanvasView(ctx.activity, emit)

    override fun call(ctx: PxModuleContext, method: String, args: JSONArray, reply: PxReply) {
        val v = (if (args.length() > 0) ctx.view(args.optInt(0, -1)) else null) as? DrawingCanvasView
            ?: run { reply(null, "The DrawingCanvas is not mounted"); return }
        try {
            when (method) {
                "undo" -> { v.canvas.undo(); reply(null, null) }
                "redo" -> { v.canvas.redo(); reply(null, null) }
                "clear" -> { v.canvas.clear(); reply(null, null) }
                "getStrokes" -> reply(v.canvas.strokes.map { it.json() }, null)
                "setStrokes" -> {
                    val list = args.optJSONArray(1) ?: JSONArray()
                    v.canvas.setStrokes((0 until list.length()).mapNotNull { Stroke.from(list.optJSONObject(it)) })
                    reply(null, null)
                }
                "toImage" -> toImage(ctx, v.canvas, args.optJSONObject(1) ?: JSONObject(), reply)
                else -> reply(null, "DrawingCanvas has no method $method")
            }
        } catch (e: Exception) {
            reply(null, e.message ?: e.toString())
        }
    }

    /** Renders the strokes again at `scale` off the main thread, finds the ink, crops and writes the file. */
    private fun toImage(ctx: PxModuleContext, c: CanvasView, o: JSONObject, reply: PxReply) {
        val k = if (o.has("scale")) o.getDouble("scale").toFloat() else c.resources.displayMetrics.density
        val list = c.strokes.toList()
        val vw = c.width / c.resources.displayMetrics.density
        val vh = c.height / c.resources.displayMetrics.density
        val bg = c.bgColor
        val jpg = o.optString("format") == "jpg"
        val trim = o.optBoolean("trim", false)
        val pad = (o.optDouble("padding", 0.0) * k).roundToInt()
        val withBackground = o.optBoolean("background", true)
        val quality = (o.optDouble("quality", 1.0) * 100).roundToInt().coerceIn(0, 100)
        val dir = File(ctx.activity.cacheDir, "DrawingCanvas")
        thread(name = "DrawingCanvas.toImage") {
            try {
                val w = maxOf(1, (vw * k).roundToInt())
                val h = maxOf(1, (vh * k).roundToInt())
                val ink = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
                val ic = Canvas(ink)
                for (s in list) s.draw(ic, k)
                var x = 0
                var y = 0
                var rw = w
                var rh = h
                if (trim) {
                    val b = inkBounds(ink) ?: run { ink.recycle(); reply(null, null); return@thread }
                    x = b[0] - pad; y = b[1] - pad; rw = b[2] + 2 * pad; rh = b[3] + 2 * pad
                }
                val out = Bitmap.createBitmap(rw, rh, Bitmap.Config.ARGB_8888)
                val oc = Canvas(out)
                if (jpg) oc.drawColor(Color.WHITE)
                if (withBackground) oc.drawColor(bg)
                oc.drawBitmap(ink, -x.toFloat(), -y.toFloat(), null)
                ink.recycle()
                dir.mkdirs()
                val file = File(dir, UUID.randomUUID().toString() + if (jpg) ".jpg" else ".png")
                file.outputStream().use {
                    out.compress(if (jpg) Bitmap.CompressFormat.JPEG else Bitmap.CompressFormat.PNG, quality, it)
                }
                out.recycle()
                reply(mapOf("uri" to "file://" + file.absolutePath, "width" to rw, "height" to rh,
                            "x" to (x / k).toDouble(), "y" to (y / k).toDouble()), null)
            } catch (e: Throwable) {
                reply(null, e.message ?: e.toString())
            }
        }
    }

    /** [x, y, width, height] of every pixel with alpha, or null for no ink. */
    private fun inkBounds(b: Bitmap): IntArray? {
        val w = b.width
        val h = b.height
        val row = IntArray(w)
        var x0 = w; var y0 = h; var x1 = -1; var y1 = -1
        for (y in 0 until h) {
            b.getPixels(row, 0, w, 0, y, w, 1)
            for (x in 0 until w) {
                if (row[x] ushr 24 != 0) {
                    if (x < x0) x0 = x
                    if (x > x1) x1 = x
                    if (y < y0) y0 = y
                    if (y > y1) y1 = y
                }
            }
        }
        return if (x1 < 0) null else intArrayOf(x0, y0, x1 - x0 + 1, y1 - y0 + 1)
    }
}
