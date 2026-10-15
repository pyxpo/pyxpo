package dev.pyxpo.modules.medialibrary

import android.Manifest
import android.app.Activity
import android.content.ContentUris
import android.content.ContentValues
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import dev.pyxpo.moduleapi.PxModule
import dev.pyxpo.moduleapi.PxModuleContext
import dev.pyxpo.moduleapi.PxReply
import org.json.JSONArray
import java.io.File
import java.util.concurrent.Executors

/**
 * Photo library permissions and adding photos and videos with their exact bytes through MediaStore.
 * Adding needs no permission on Android 10+; reading needs READ_MEDIA_IMAGES/VIDEO (13+) or READ_EXTERNAL_STORAGE.
 */
class MediaLibraryModule : PxModule() {
    override val name = "MediaLibrary"

    override fun call(ctx: PxModuleContext, method: String, args: JSONArray, reply: PxReply) {
        when (method) {
            "get_permission" -> reply(state(ctx.activity, args.optBoolean(0, false)), null)
            "request_permission" -> {
                val writeOnly = args.optBoolean(0, false)
                val a = ctx.activity
                val now = state(a, writeOnly)
                if (now["status"] == "granted" || now["canAskAgain"] != true) { reply(now, null); return }
                val perms = required(writeOnly) + if (!writeOnly && Build.VERSION.SDK_INT >= 34) listOf(USER_SELECTED) else emptyList()
                ctx.requestPermissions(perms.toTypedArray()) { _ ->
                    prefs(a).edit().apply { perms.forEach { putBoolean(it, true) } }.apply()
                    reply(state(a, writeOnly), null)
                }
            }
            "save", "create" -> {
                val raw = args.optString(0)
                val src = File(if (raw.startsWith("file://")) android.net.Uri.parse(raw).path ?: raw else raw)
                if (!src.isFile) { reply(null, "file not found: ${src.name}"); return }
                val describe = method == "create"
                if (Build.VERSION.SDK_INT >= 29) saveAsync(ctx, src, describe, reply)
                else ctx.requestPermissions(arrayOf(Manifest.permission.WRITE_EXTERNAL_STORAGE)) { r ->
                    prefs(ctx.activity).edit().putBoolean(Manifest.permission.WRITE_EXTERNAL_STORAGE, true).apply()
                    if (r.values.firstOrNull() == true) saveAsync(ctx, src, describe, reply) else reply(null, "storage permission denied")
                }
            }
            else -> reply(null, "unknown native call MediaLibrary.$method")
        }
    }

    // permissions

    private fun required(writeOnly: Boolean): List<String> = when {
        Build.VERSION.SDK_INT <= 28 ->
            if (writeOnly) listOf(Manifest.permission.WRITE_EXTERNAL_STORAGE)
            else listOf(Manifest.permission.READ_EXTERNAL_STORAGE, Manifest.permission.WRITE_EXTERNAL_STORAGE)
        writeOnly -> emptyList()
        Build.VERSION.SDK_INT >= 33 -> listOf(Manifest.permission.READ_MEDIA_IMAGES, Manifest.permission.READ_MEDIA_VIDEO)
        else -> listOf(Manifest.permission.READ_EXTERNAL_STORAGE)
    }

    private fun prefs(a: Activity) = a.getSharedPreferences("pyxpo.permissions", Context.MODE_PRIVATE)

    private fun granted(a: Activity, p: String) = a.checkSelfPermission(p) == PackageManager.PERMISSION_GRANTED

    /** Expo status: never asked is `undetermined`; denied can be asked again until Android stops showing the dialog. */
    private fun state(a: Activity, writeOnly: Boolean): Map<String, Any> {
        val missing = required(writeOnly).filterNot { granted(a, it) }
        if (missing.isEmpty()) return mapOf("status" to "granted", "canAskAgain" to true, "accessPrivileges" to "all")
        // Android 14+: the user allowed only some photos and videos.
        if (!writeOnly && Build.VERSION.SDK_INT >= 34 && granted(a, USER_SELECTED)) {
            return mapOf("status" to "granted", "canAskAgain" to true, "accessPrivileges" to "limited")
        }
        val p = prefs(a)
        if (missing.any { !p.getBoolean(it, false) }) return mapOf("status" to "undetermined", "canAskAgain" to true, "accessPrivileges" to "none")
        return mapOf("status" to "denied", "canAskAgain" to missing.any { a.shouldShowRequestPermissionRationale(it) }, "accessPrivileges" to "none")
    }

    // adding

    private fun mimeOf(f: File) = when (f.extension.lowercase()) {
        "png" -> "image/png"
        "webp" -> "image/webp"
        "heic" -> "image/heic"
        "heif" -> "image/heif"
        "gif" -> "image/gif"
        "mp4", "m4v" -> "video/mp4"
        "mov" -> "video/quicktime"
        "3gp" -> "video/3gpp"
        "webm" -> "video/webm"
        "mkv" -> "video/x-matroska"
        else -> "image/jpeg"
    }

    private fun saveAsync(ctx: PxModuleContext, src: File, describe: Boolean, reply: PxReply) {
        val app = ctx.activity.applicationContext
        executor.execute {
            try {
                val asset = save(app, src)
                reply(if (describe) asset else null, null)
            } catch (e: Throwable) { reply(null, e.message ?: e.toString()) }
        }
    }

    @Suppress("DEPRECATION")
    private fun save(app: Context, src: File): Map<String, Any?> {
        val cr = app.contentResolver
        val mime = mimeOf(src)
        val video = mime.startsWith("video/")
        val folder = if (video) Environment.DIRECTORY_MOVIES else Environment.DIRECTORY_PICTURES
        val collection = if (video) MediaStore.Video.Media.EXTERNAL_CONTENT_URI else MediaStore.Images.Media.EXTERNAL_CONTENT_URI
        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, src.name)
            put(MediaStore.MediaColumns.MIME_TYPE, mime)
            if (Build.VERSION.SDK_INT >= 29) {
                put(MediaStore.MediaColumns.RELATIVE_PATH, folder)
                put(MediaStore.MediaColumns.IS_PENDING, 1)
            } else {
                val dir = Environment.getExternalStoragePublicDirectory(folder).apply { mkdirs() }
                put(MediaStore.MediaColumns.DATA, unique(dir, src.name).absolutePath)
            }
        }
        val uri = cr.insert(collection, values) ?: throw java.io.IOException("cannot create library entry")
        try {
            (cr.openOutputStream(uri) ?: throw java.io.IOException("cannot open library entry")).use { o -> src.inputStream().use { it.copyTo(o) } }
            if (Build.VERSION.SDK_INT >= 29) {
                val done = ContentValues().apply { put(MediaStore.MediaColumns.IS_PENDING, 0) }
                try {
                    cr.update(uri, done, null, null)
                } catch (e: IllegalStateException) {
                    // MediaStore gives up after 32 "name (n).ext" clashes when it publishes the file; use a timestamped name.
                    done.put(MediaStore.MediaColumns.DISPLAY_NAME, "${src.nameWithoutExtension}_${System.currentTimeMillis()}" +
                        (if (src.extension.isEmpty()) "" else ".${src.extension}"))
                    cr.update(uri, done, null, null)
                }
            }
        } catch (e: Throwable) {
            cr.delete(uri, null, null)
            throw e
        }
        // MediaStore may rename on a clash ("a (1).jpg"); the app owns the row, so it can read it back without permission.
        var filename = src.name
        cr.query(uri, arrayOf(MediaStore.MediaColumns.DISPLAY_NAME), null, null, null)?.use { if (it.moveToFirst()) it.getString(0)?.let { n -> filename = n } }
        val (w, h, ms) = measure(src, video)
        return mapOf("id" to ContentUris.parseId(uri).toString(), "uri" to uri.toString(), "mediaType" to if (video) "video" else "photo",
            "width" to w, "height" to h, "duration" to ms / 1000.0, "filename" to filename)
    }

    private fun unique(dir: File, name: String): File {
        var f = File(dir, name)
        var i = 1
        while (f.exists()) { f = File(dir, "${name.substringBeforeLast('.')} ($i).${name.substringAfterLast('.', "")}".removeSuffix(".")); i++ }
        return f
    }

    /** Display width, height and duration in milliseconds of the source file. */
    private fun measure(src: File, video: Boolean): Triple<Int, Int, Long> {
        if (video) {
            val r = android.media.MediaMetadataRetriever()
            try {
                r.setDataSource(src.path)
                fun num(key: Int) = r.extractMetadata(key)?.toLongOrNull() ?: 0L
                val rot = num(android.media.MediaMetadataRetriever.METADATA_KEY_VIDEO_ROTATION)
                val w = num(android.media.MediaMetadataRetriever.METADATA_KEY_VIDEO_WIDTH).toInt()
                val h = num(android.media.MediaMetadataRetriever.METADATA_KEY_VIDEO_HEIGHT).toInt()
                val swap = rot == 90L || rot == 270L
                return Triple(if (swap) h else w, if (swap) w else h, num(android.media.MediaMetadataRetriever.METADATA_KEY_DURATION))
            } catch (e: Exception) {
                return Triple(0, 0, 0L)
            } finally {
                r.release()
            }
        }
        val o = android.graphics.BitmapFactory.Options().apply { inJustDecodeBounds = true }
        android.graphics.BitmapFactory.decodeFile(src.path, o)
        val ori = try {
            android.media.ExifInterface(src.path).getAttributeInt(android.media.ExifInterface.TAG_ORIENTATION, 1)
        } catch (e: Exception) { 1 }
        val swap = ori in 5..8
        return Triple(maxOf(0, if (swap) o.outHeight else o.outWidth), maxOf(0, if (swap) o.outWidth else o.outHeight), 0L)
    }

    companion object {
        private const val USER_SELECTED = "android.permission.READ_MEDIA_VISUAL_USER_SELECTED"
        private val executor = Executors.newSingleThreadExecutor { r -> Thread(r, "pyxpo-medialibrary") }
    }
}
