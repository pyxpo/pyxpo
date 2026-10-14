package dev.pyxpo.runtime

import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log
import java.io.File
import java.util.zip.ZipInputStream

/** Extracts bundled Python assets, runs CPython on a dedicated thread, relays ops/events. */
class PyxpoRuntime(private val ctx: Context, private val applier: OpApplier) {
    private val ui = Handler(Looper.getMainLooper())
    @Volatile private var started = false

    init { System.loadLibrary("pyxpo_jni") }

    private external fun nativeSetEnv(k: String, v: String)
    private external fun nativeStart(home: String, paths: String, module: String): Int
    private external fun nativeDispatchEvent(json: String)

    /** Called from the Python thread via JNI. */
    @Suppress("unused")
    fun onOps(json: String) { ui.post { applier.apply(json) } }

    /** Called on the UI thread; the bridge takes the GIL, so run off-thread to avoid UI stalls. */
    fun sendEvent(json: String) { events.execute { nativeDispatchEvent(json) } }

    private val events = java.util.concurrent.Executors.newSingleThreadExecutor()

    fun start(module: String = "app.main", devEnv: Map<String, String> = emptyMap()) {
        if (started) return
        started = true
        val abi = Build.SUPPORTED_ABIS.first { it == "arm64-v8a" || it == "x86_64" }
        // 8 MB stack: CPython recursion + numpy imports need more than the default
        Thread(null, {
            val root = extract(abi)
            val home = File(root, "home").absolutePath
            val site = File(root, "site").absolutePath
            val app = File(root, "app").absolutePath
            nativeSetEnv("PYXPO_TARGET", "android")
            nativeSetEnv("HOME", ctx.filesDir.absolutePath)
            nativeSetEnv("TMPDIR", ctx.cacheDir.absolutePath)
            nativeSetEnv("PYXPO_NATIVE_LIB_DIR", ctx.applicationInfo.nativeLibraryDir)
            for ((k, v) in devEnv) nativeSetEnv(k, v)
            val rc = nativeStart(home, "$app:$site", module)
            Log.i("pyxpo", "python exited rc=$rc")
        }, "PyxpoPython", 8L * 1024 * 1024).start()
    }

    private fun extract(abi: String): File {
        val hash = ctx.assets.open("pyxpo/manifest.txt").bufferedReader().readText().trim()
        val root = File(ctx.filesDir, "pyxpo/$hash")
        val done = File(root, ".done")
        if (done.exists()) return root
        File(ctx.filesDir, "pyxpo").deleteRecursively()
        root.mkdirs()
        unzip("pyxpo/stdlib-$abi.zip", File(root, "home"))
        unzip("pyxpo/site-$abi.zip", File(root, "site"))
        unzip("pyxpo/app.zip", File(root, "app"))
        done.writeText("ok")
        return root
    }

    private fun unzip(asset: String, dest: File) {
        dest.mkdirs()
        ZipInputStream(ctx.assets.open(asset).buffered()).use { zin ->
            var e = zin.nextEntry
            while (e != null) {
                val out = File(dest, e.name)
                require(out.canonicalPath.startsWith(dest.canonicalPath + File.separator)) { "zip slip: ${e.name}" }
                if (e.isDirectory) out.mkdirs() else {
                    out.parentFile?.mkdirs()
                    out.outputStream().use { zin.copyTo(it) }
                }
                e = zin.nextEntry
            }
        }
    }
}
