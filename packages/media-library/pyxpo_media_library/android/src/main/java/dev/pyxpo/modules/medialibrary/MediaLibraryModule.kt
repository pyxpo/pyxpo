package dev.pyxpo.modules.medialibrary

import android.content.ContentValues
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import dev.pyxpo.moduleapi.PxModule
import dev.pyxpo.moduleapi.PxModuleContext
import dev.pyxpo.moduleapi.PxReply
import org.json.JSONArray
import java.io.File
import java.util.concurrent.Executors

/** Saves files to the shared Pictures folder with their exact bytes. Android 10+ needs no permission. */
class MediaLibraryModule : PxModule() {
    override val name = "MediaLibrary"

    override fun call(ctx: PxModuleContext, method: String, args: JSONArray, reply: PxReply) {
        when (method) {
            "request_permission" -> {
                if (Build.VERSION.SDK_INT >= 29) reply(mapOf("granted" to true), null)
                else ctx.requestPermissions(arrayOf(android.Manifest.permission.WRITE_EXTERNAL_STORAGE)) { r ->
                    reply(mapOf("granted" to (r.values.firstOrNull() == true)), null)
                }
            }
            "save" -> {
                val raw = args.optString(0)
                val src = File(if (raw.startsWith("file://")) android.net.Uri.parse(raw).path ?: raw else raw)
                if (!src.isFile) { reply(null, "file not found: ${src.name}"); return }
                if (Build.VERSION.SDK_INT >= 29) saveAsync(ctx, src, reply)
                else ctx.requestPermissions(arrayOf(android.Manifest.permission.WRITE_EXTERNAL_STORAGE)) { r ->
                    if (r.values.firstOrNull() == true) saveAsync(ctx, src, reply) else reply(null, "storage permission denied")
                }
            }
            else -> reply(null, "unknown native call MediaLibrary.$method")
        }
    }

    private fun mimeOf(f: File) = when (f.extension.lowercase()) {
        "png" -> "image/png"
        "webp" -> "image/webp"
        "heic" -> "image/heic"
        "heif" -> "image/heif"
        "gif" -> "image/gif"
        else -> "image/jpeg"
    }

    private fun saveAsync(ctx: PxModuleContext, src: File, reply: PxReply) {
        val app = ctx.activity.applicationContext
        executor.execute {
            try { save(app, src); reply(null, null) } catch (e: Throwable) { reply(null, e.message ?: e.toString()) }
        }
    }

    @Suppress("DEPRECATION")
    private fun save(app: android.content.Context, src: File) {
        val cr = app.contentResolver
        val mime = mimeOf(src)
        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, src.name)
            put(MediaStore.MediaColumns.MIME_TYPE, mime)
            if (Build.VERSION.SDK_INT >= 29) {
                put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_PICTURES)
                put(MediaStore.MediaColumns.IS_PENDING, 1)
            } else {
                val dir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES).apply { mkdirs() }
                put(MediaStore.MediaColumns.DATA, File(dir, src.name).absolutePath)
            }
        }
        val uri = cr.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values) ?: throw java.io.IOException("cannot create library entry")
        try {
            (cr.openOutputStream(uri) ?: throw java.io.IOException("cannot open library entry")).use { o -> src.inputStream().use { it.copyTo(o) } }
            if (Build.VERSION.SDK_INT >= 29) {
                cr.update(uri, ContentValues().apply { put(MediaStore.MediaColumns.IS_PENDING, 0) }, null, null)
            }
        } catch (e: Throwable) {
            cr.delete(uri, null, null)
            throw e
        }
    }

    companion object {
        private val executor = Executors.newSingleThreadExecutor { r -> Thread(r, "pyxpo-medialibrary") }
    }
}
