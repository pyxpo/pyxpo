package dev.pyxpo.runtime

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.ColorSpace
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Base64
import android.util.LruCache
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.util.concurrent.Executors

/**
 * Loads images off the UI thread: files, `asset:name`, `data:` URIs and http(s) URLs (disk cached).
 * Decoded bitmaps live in a memory cache of 1/8 of the heap. Images are subsampled to the view size when the caller
 * knows it (a 800 px photo in a 56 dp thumb decodes at 200 px), else huge images to the screen size.
 */
class Images(private val ctx: Context) {
    private val main = Handler(Looper.getMainLooper())
    private val pool = Executors.newFixedThreadPool(4)
    private val mem = object : LruCache<String, Bitmap>((Runtime.getRuntime().maxMemory() / 8).toInt()) {
        override fun sizeOf(key: String, value: Bitmap) = value.byteCount
    }
    private val disk = File(ctx.cacheDir, "pyxpo_img").also { it.mkdirs() }
    private val cap: Int = ctx.resources.displayMetrics.let { maxOf(it.widthPixels, it.heightPixels) * 2 }

    // full size of each source in px, for the load event (the cached bitmap may be subsampled)
    private val sizes = java.util.concurrent.ConcurrentHashMap<String, IntArray>()

    /**
     * Calls [done] on the UI thread with a bitmap and the source's full size in px, or an error message.
     * [tw] x [th] is the view size in px; 0 means unknown, so only huge images are subsampled.
     */
    fun load(uri: String, tw: Int, th: Int, done: (Bitmap?, Int, Int, String?) -> Unit) {
        val key = if (tw > 0 && th > 0) "$uri@${tw}x$th" else uri
        mem.get(key)?.let { b -> val sz = sizes[uri]; done(b, sz?.get(0) ?: b.width, sz?.get(1) ?: b.height, null); return }
        pool.execute {
            var bmp: Bitmap? = null
            var err: String? = null
            try {
                bmp = decode(uri, tw, th)
                if (bmp == null) err = "could not decode image"
            } catch (e: Exception) {
                err = e.message ?: e.javaClass.simpleName
            }
            if (bmp != null) mem.put(key, bmp)
            val sz = sizes[uri]
            main.post { done(bmp, sz?.get(0) ?: bmp?.width ?: 0, sz?.get(1) ?: bmp?.height ?: 0, err) }
        }
    }

    private fun decode(uri: String, tw: Int, th: Int): Bitmap? = when {
        uri.startsWith("data:") -> {
            val raw = Base64.decode(uri.substringAfter("base64,"), Base64.DEFAULT)
            sample(uri, tw, th) { BitmapFactory.decodeByteArray(raw, 0, raw.size, it) }
        }
        uri.startsWith("asset:") -> {
            val name = uri.removePrefix("asset:")
            val bytes = ctx.assets.open(name).use { it.readBytes() }
            sample(uri, tw, th) { BitmapFactory.decodeByteArray(bytes, 0, bytes.size, it) }
        }
        uri.startsWith("http://") || uri.startsWith("https://") -> {
            val f = File(disk, sha1(uri))
            if (!f.exists()) download(uri, f)
            sample(uri, tw, th) { BitmapFactory.decodeFile(f.path, it) }
        }
        else -> sample(uri, tw, th) { BitmapFactory.decodeFile(uri.removePrefix("file://"), it) }
    }

    private fun sample(uri: String, tw: Int, th: Int, run: (BitmapFactory.Options) -> Bitmap?): Bitmap? {
        val b = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        run(b)
        if (b.outWidth > 0 && b.outHeight > 0) sizes[uri] = intArrayOf(b.outWidth, b.outHeight)
        return run(srgb(BitmapFactory.Options().apply { inSampleSize = sampleSize(b.outWidth, b.outHeight, tw, th, cap) }))
    }

    /** Decode into sRGB: wide-gamut bitmaps (Display P3 iPhone photos) draw blank on some GPUs. */
    private fun srgb(o: BitmapFactory.Options): BitmapFactory.Options {
        if (Build.VERSION.SDK_INT >= 26) o.inPreferredColorSpace = ColorSpace.get(ColorSpace.Named.SRGB)
        return o
    }

    private fun download(url: String, to: File) {
        var u = url
        for (hop in 0 until 5) {
            val c = URL(u).openConnection() as HttpURLConnection
            c.connectTimeout = 15000; c.readTimeout = 20000; c.instanceFollowRedirects = true
            try {
                val code = c.responseCode
                if (code in 300..399) {
                    val loc = c.getHeaderField("Location") ?: throw RuntimeException("bad redirect")
                    val next = URL(URL(u), loc)  // Location may be relative
                    if (u.startsWith("https:") && next.protocol != "https") throw RuntimeException("insecure redirect")
                    u = next.toString(); continue
                }
                if (code !in 200..299) throw RuntimeException("HTTP $code")
                // Unique temp file: two loads of the same URL must not write into one .part file.
                val tmp = File.createTempFile("pxdl", ".part", to.parentFile)
                try {
                    c.inputStream.use { i -> tmp.outputStream().use { o -> i.copyTo(o) } }
                    if (!tmp.renameTo(to) && !to.exists()) throw RuntimeException("cache write failed")
                } finally { tmp.delete() }
                return
            } finally { c.disconnect() }
        }
        throw RuntimeException("too many redirects")
    }

    companion object {
        /** Largest power of two that keeps the decoded image at least [tw] x [th] (so cover still fills) and within [cap]. */
        fun sampleSize(w: Int, h: Int, tw: Int, th: Int, cap: Int): Int {
            var s = 1
            while (w / s > cap || h / s > cap) s *= 2
            if (tw > 0 && th > 0) while (w / (s * 2) >= tw && h / (s * 2) >= th) s *= 2
            return s
        }
    }

    private fun sha1(s: String) = MessageDigest.getInstance("SHA-1").digest(s.toByteArray()).joinToString("") { "%02x".format(it) }
}
