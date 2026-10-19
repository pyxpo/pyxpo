package dev.pyxpo.runtime

import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log
import java.io.File
import java.util.zip.ZipInputStream

/**
 * Extracts bundled Python assets, runs CPython on a dedicated thread, relays ops/events.
 * One per process: CPython starts once. A new activity (theme overlay, config change) attaches its applier with [attach].
 * A service can start Python with no activity ([startHeadless], through `PxProcess.start`): native module calls then
 * go to a host without an activity and tree ops are dropped until an activity attaches and remounts the app.
 */
class PyxpoRuntime private constructor(context: Context) {
    companion object {
        private var instance: PyxpoRuntime? = null  // UI thread only

        /** The process runtime, made on first use. Main thread. */
        fun get(context: Context): PyxpoRuntime = instance ?: PyxpoRuntime(context).also { instance = it }

        /** `PxProcess.start`: runs Python if it does not run yet, with no activity. Main thread. */
        @JvmStatic
        fun startHeadless(context: Context) { get(context).start() }
    }

    private val ctx = context.applicationContext
    private val ui = Handler(Looper.getMainLooper())
    @Volatile private var started = false
    private var applier: OpApplier? = null  // UI thread only
    private var epoch = 0

    init {
        System.loadLibrary("pyxpo_jni")
        dev.pyxpo.moduleapi.PxProcess.sink = { name, payload ->
            val data = org.json.JSONObject.wrap(payload) as? org.json.JSONObject ?: org.json.JSONObject()
            ui.post { sendEvent(moduleEvent(name, data)) }
        }
    }

    private fun moduleEvent(name: String, data: org.json.JSONObject): String = org.json.JSONObject().put("event", "module")
        .put("id", 0).put("payload", org.json.JSONObject().put("name", name).put("data", data)).toString()

    /** Serves native module calls while no activity is attached. */
    private val headless by lazy { PxModuleHost(ctx, null) { name, data -> sendEvent(moduleEvent(name, data)) } }

    /**
     * Points ops at a new activity's applier. Once Python runs, it gets a `remount` event: it mounts the whole tree
     * again and answers with a `mark` op; the applier drops tree ops sent for the old activity until then.
     */
    fun attach(a: OpApplier, env: org.json.JSONObject) {
        applier = a
        if (!started) return  // first start: Python mounts into this applier
        // Python already ran, for an activity before this one or headless for a service
        epoch++
        a.awaitMark(epoch)
        sendEvent(org.json.JSONObject().put("id", 0).put("event", "remount")
            .put("payload", org.json.JSONObject().put("n", epoch).put("env", env)).toString())
    }

    /** The activity of `a` is gone: ops go to the headless host until the next one attaches. */
    fun detach(a: OpApplier) {
        if (applier === a) applier = null
    }

    private external fun nativeSetEnv(k: String, v: String)
    private external fun nativeStart(home: String, paths: String, module: String): Int
    private external fun nativeDispatchEvent(json: String)

    /** Called from the Python thread via JNI. */
    @Suppress("unused")
    fun onOps(json: String) {
        ui.post {
            // first ops batch proves the Python handler is registered: flush events queued before startup
            if (!ready) { ready = true; for (e in pending) events.execute { nativeDispatchEvent(e) }; pending.clear() }
            val a = applier
            if (a != null) a.apply(json) else applyHeadless(json)
        }
    }

    /** No activity: only `call` ops mean something (tree ops go to the next activity's remount). */
    private fun applyHeadless(batch: String) {
        val ops = org.json.JSONArray(batch)
        for (i in 0 until ops.length()) {
            val o = ops.getJSONObject(i)
            if (o.optString("op") != "call") continue
            val id = o.getInt("id")
            val module = o.getString("module")
            val method = o.getString("method")
            val wantReply = o.optBoolean("reply")
            fun reply(v: Any?, e: String?) {
                if (!wantReply) return
                val p = org.json.JSONObject()
                if (e != null) p.put("error", e) else p.put("value", v ?: org.json.JSONObject.NULL)
                sendEvent(org.json.JSONObject().put("event", "call_result").put("id", id).put("payload", p).toString())
            }
            if (!headless.call(module, method, o.optJSONArray("args") ?: org.json.JSONArray()) { v, e -> reply(v, e) })
                reply(null, "$module.$method needs the app on screen: Python runs headless (a service started it)")
        }
    }

    private var ready = false  // UI thread only
    private val pending = ArrayList<String>()

    /** Called on the UI thread; the bridge takes the GIL, so run off-thread to avoid UI stalls. */
    fun sendEvent(json: String) {
        if (!ready) { pending.add(json); return }
        events.execute { nativeDispatchEvent(json) }
    }

    private val events = java.util.concurrent.Executors.newSingleThreadExecutor()

    fun start(module: String = "pyxpo.router.entry", devEnv: Map<String, String> = emptyMap()) {
        if (started) return
        started = true
        // the first ABI the phone runs that the APK ships, the same pick Android makes for the native libs
        val shipped = ctx.assets.list("pyxpo")?.toSet() ?: emptySet()
        val abi = Build.SUPPORTED_ABIS.first { "stdlib-$it.zip" in shipped }
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
