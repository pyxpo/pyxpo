package dev.pyxpo.runtime

import android.app.Activity
import android.os.Bundle
import android.widget.FrameLayout

class MainActivity : Activity() {
    private var runtime: PyxpoRuntime? = null
    private var applier: OpApplier? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = FrameLayout(this)
        // targetSdk 35+ draws edge-to-edge; inset the root so content clears status/action bars.
        root.setOnApplyWindowInsetsListener { v, insets ->
            val top = if (android.os.Build.VERSION.SDK_INT >= 30)
                insets.getInsets(android.view.WindowInsets.Type.systemBars()).top else insets.systemWindowInsetTop
            val bottom = if (android.os.Build.VERSION.SDK_INT >= 30)
                insets.getInsets(android.view.WindowInsets.Type.systemBars()).bottom else insets.systemWindowInsetBottom
            v.setPadding(0, top, 0, bottom)
            insets
        }
        setContentView(root)
        lateinit var rt: PyxpoRuntime
        val applier = OpApplier(this, root) { json -> rt.sendEvent(json) }
        this.applier = applier
        rt = PyxpoRuntime(this, applier)
        runtime = rt
        // Hot-reload endpoint is honoured in debuggable builds only.
        val dev = HashMap<String, String>()
        dev["PYXPO_WIRE"] = "2"
        val dm = resources.displayMetrics
        dev["PYXPO_ENV"] = OpApplier.envJson(this, dm.widthPixels, dm.heightPixels).toString()
        val debuggable = (applicationInfo.flags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0
        val url = intent?.getStringExtra("pyxpo_dev_url")
        if (debuggable && url != null) {
            dev["PYXPO_DEV_URL"] = url
            dev["PYXPO_DEV_TOKEN"] = intent?.getStringExtra("pyxpo_dev_token") ?: ""
        }
        rt.start(devEnv = dev)
    }

    override fun onConfigurationChanged(newConfig: android.content.res.Configuration) {
        super.onConfigurationChanged(newConfig)
        applier?.configChanged()
    }
}
