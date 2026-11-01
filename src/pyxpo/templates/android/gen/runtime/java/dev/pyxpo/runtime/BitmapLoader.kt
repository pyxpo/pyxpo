package dev.pyxpo.runtime

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.media.ExifInterface
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.util.Base64
import java.io.File
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLDecoder
import java.security.MessageDigest
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/**
 * Loads `http(s)://` (cached on disk in the app cache), `content://`, `file://`, plain path and `data:` images on
 * a background thread, scaled down so the longer side is at most `maxSide`. Calls back on the main thread.
 */
internal class BitmapLoader(context: Context) {
    private val app = context.applicationContext
    private val pool: ExecutorService = Executors.newFixedThreadPool(2)
    private val main = Handler(Looper.getMainLooper())
    private val cacheDir = File(app.cacheDir, "pyxpo-image-viewer")

    fun load(uri: String, maxSide: Int, done: (Bitmap?) -> Unit) {
        if (pool.isShutdown) return
        pool.execute {
            val bitmap = try { decode(uri, maxSide.coerceIn(1024, 4096)) } catch (e: Exception) { null } catch (e: OutOfMemoryError) { null }
            main.post { done(bitmap) }
        }
    }

    fun shutdown() {
        pool.shutdownNow()
    }

    private fun decode(uri: String, maxSide: Int): Bitmap? = when {
        uri.startsWith("http://") || uri.startsWith("https://") -> download(uri)?.let { fromFile(it, maxSide) }
        uri.startsWith("data:") -> fromBytes(dataBytes(uri), maxSide)
        uri.startsWith("content://") -> {
            val u = Uri.parse(uri)
            fromStreams({ app.contentResolver.openInputStream(u) }, maxSide)
        }
        else -> fromFile(File(if (uri.startsWith("file://")) Uri.parse(uri).path ?: uri else uri), maxSide)
    }

    private fun download(url: String): File? {
        cacheDir.mkdirs()
        val name = MessageDigest.getInstance("SHA-1").digest(url.toByteArray()).joinToString("") { "%02x".format(it) }
        val file = File(cacheDir, name)
        if (file.length() > 0) return file
        var conn: HttpURLConnection? = null
        try {
            var target = URL(url)
            for (hop in 0 until 5) {  // HttpURLConnection does not follow http <-> https redirects itself
                conn = (target.openConnection() as HttpURLConnection).apply {
                    connectTimeout = 15000
                    readTimeout = 30000
                    instanceFollowRedirects = true
                }
                val code = conn.responseCode
                if (code in 300..399) {
                    val next = conn.getHeaderField("Location") ?: return null
                    target = URL(target, next)
                    conn.disconnect()
                    continue
                }
                if (code !in 200..299) return null
                val tmp = File(cacheDir, "$name.part")
                conn.inputStream.use { input -> tmp.outputStream().use { input.copyTo(it) } }
                return if (tmp.renameTo(file)) file else null
            }
            return null
        } finally {
            conn?.disconnect()
        }
    }

    private fun dataBytes(uri: String): ByteArray {
        val comma = uri.indexOf(',')
        require(comma > 0) { "bad data URI" }
        val meta = uri.substring(5, comma)
        val body = uri.substring(comma + 1)
        return if (meta.endsWith(";base64")) Base64.decode(body, Base64.DEFAULT) else URLDecoder.decode(body, "UTF-8").toByteArray()
    }

    private fun sample(w: Int, h: Int, maxSide: Int): Int {
        var s = 1
        while (max(w, h) / (s * 2) >= maxSide) s *= 2
        return s
    }

    private fun max(a: Int, b: Int) = if (a > b) a else b

    private fun fromBytes(bytes: ByteArray, maxSide: Int): Bitmap? {
        val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, o)
        if (o.outWidth <= 0) return null
        val opts = BitmapFactory.Options().apply { inSampleSize = sample(o.outWidth, o.outHeight, maxSide) }
        return BitmapFactory.decodeByteArray(bytes, 0, bytes.size, opts)
    }

    private fun fromStreams(open: () -> InputStream?, maxSide: Int): Bitmap? {
        val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        open()?.use { BitmapFactory.decodeStream(it, null, o) } ?: return null
        if (o.outWidth <= 0) return null
        val opts = BitmapFactory.Options().apply { inSampleSize = sample(o.outWidth, o.outHeight, maxSide) }
        val bitmap = open()?.use { BitmapFactory.decodeStream(it, null, opts) } ?: return null
        val rotation = open()?.use { orientation(ExifInterface(it)) } ?: 0
        return rotate(bitmap, rotation)
    }

    private fun fromFile(file: File, maxSide: Int): Bitmap? {
        if (!file.isFile) return null
        val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(file.path, o)
        if (o.outWidth <= 0) return null
        val opts = BitmapFactory.Options().apply { inSampleSize = sample(o.outWidth, o.outHeight, maxSide) }
        val bitmap = BitmapFactory.decodeFile(file.path, opts) ?: return null
        val rotation = try { orientation(ExifInterface(file.path)) } catch (e: Exception) { 0 }
        return rotate(bitmap, rotation)
    }

    private fun orientation(exif: ExifInterface): Int = when (exif.getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)) {
        ExifInterface.ORIENTATION_ROTATE_90 -> 90
        ExifInterface.ORIENTATION_ROTATE_180 -> 180
        ExifInterface.ORIENTATION_ROTATE_270 -> 270
        else -> 0
    }

    private fun rotate(bitmap: Bitmap, degrees: Int): Bitmap {
        if (degrees == 0) return bitmap
        val m = Matrix().apply { postRotate(degrees.toFloat()) }
        return Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, m, true)
    }
}
