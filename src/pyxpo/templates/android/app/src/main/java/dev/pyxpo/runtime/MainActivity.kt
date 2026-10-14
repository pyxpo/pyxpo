package dev.pyxpo.runtime

import android.app.Activity
import android.os.Bundle
import android.widget.FrameLayout

class MainActivity : Activity() {
    private var runtime: PyxpoRuntime? = null

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
        rt = PyxpoRuntime(this, applier)
        runtime = rt
        rt.start()
    }
}
