package dev.pyxpo.runtime

import android.app.Activity
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.FrameMetrics
import android.view.Window

/** Frame-time probe. Start the activity with `--ez pyxpo_perf true` to log p50/p95/p99 frame ms and jank per 30 frames. */
object PxPerf {
    fun attach(a: Activity) {
        if (Build.VERSION.SDK_INT < 24 || !a.intent.getBooleanExtra("pyxpo_perf", false)) return
        val ms = DoubleArray(30)
        var n = 0
        var jank = 0
        @Suppress("DEPRECATION")
        val disp = if (Build.VERSION.SDK_INT >= 30) a.display else a.windowManager.defaultDisplay  // Activity.getDisplay() is API 30
        val budget = 1000.0 / (disp?.refreshRate ?: 60f).toDouble()
        a.window.decorView.post { a.window.addOnFrameMetricsAvailableListener(Window.OnFrameMetricsAvailableListener { _, m, _ ->
            ms[n++] = m.getMetric(FrameMetrics.TOTAL_DURATION) / 1e6
            if (ms[n - 1] > budget) jank++
            if (n == ms.size) {
                val s = ms.sortedArray()
                Log.i("PxPerf", "frames=30 p50=%.1f p95=%.1f p99=%.1f max=%.1f jank=%d budget=%.1f".format(
                    s[14], s[28], s[29], s[29], jank, budget))
                n = 0; jank = 0
            }
        }, Handler(Looper.getMainLooper())) }
    }
}
