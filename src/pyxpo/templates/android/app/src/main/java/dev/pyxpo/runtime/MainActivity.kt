package dev.pyxpo.runtime

import android.app.Activity
import android.os.Bundle
import android.widget.FrameLayout
import kotlin.math.max

class MainActivity : Activity() {
    private var runtime: PyxpoRuntime? = null
    private var applier: OpApplier? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = FrameLayout(this)
        // Edge-to-edge: the app draws under system bars. Insets and keyboard height go to Python (SafeArea).
        if (android.os.Build.VERSION.SDK_INT >= 30) window.setDecorFitsSystemWindows(false)
        window.statusBarColor = android.graphics.Color.TRANSPARENT
        window.navigationBarColor = android.graphics.Color.TRANSPARENT
        if (android.os.Build.VERSION.SDK_INT >= 29) {
            window.isNavigationBarContrastEnforced = false
            window.isStatusBarContrastEnforced = false
        }
        if (android.os.Build.VERSION.SDK_INT >= 23) {
            // Ask for the display's highest refresh rate at the current resolution (90/120 Hz panels).
            val d = windowManager.defaultDisplay
            val cur = d.mode
            d.supportedModes.filter { it.physicalWidth == cur.physicalWidth && it.physicalHeight == cur.physicalHeight }
                .maxByOrNull { it.refreshRate }?.let { window.attributes = window.attributes.also { a -> a.preferredDisplayModeId = it.modeId } }
        }
        root.setOnApplyWindowInsetsListener { v, insets ->
            var l = 0; var t = 0; var r = 0; var b = 0; var kb = 0
            if (android.os.Build.VERSION.SDK_INT >= 30) {
                val sb = insets.getInsets(android.view.WindowInsets.Type.systemBars() or android.view.WindowInsets.Type.displayCutout())
                l = sb.left; t = sb.top; r = sb.right; b = sb.bottom
                if (insets.isVisible(android.view.WindowInsets.Type.ime())) kb = insets.getInsets(android.view.WindowInsets.Type.ime()).bottom
            } else {
                l = insets.systemWindowInsetLeft; t = insets.systemWindowInsetTop
                r = insets.systemWindowInsetRight; b = insets.systemWindowInsetBottom
                val vis = android.graphics.Rect(); window.decorView.getWindowVisibleDisplayFrame(vis)
                kb = max(0, v.rootView.height - vis.bottom).let { if (it > v.rootView.height / 5) it else 0 }
                if (kb > 0) b = 0
            }
            applier?.setInsets(l, t, r, b, kb)
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

    @Deprecated("Deprecated in Java")
    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) applier?.applyStatusBar()
    }

    override fun onBackPressed() {
        if (applier?.handleBack() != true) @Suppress("DEPRECATION") super.onBackPressed()
    }

    override fun onConfigurationChanged(newConfig: android.content.res.Configuration) {
        super.onConfigurationChanged(newConfig)
        applier?.configChanged()
    }
}
