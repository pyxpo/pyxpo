package dev.pyxpo.runtime

import android.content.Context
import android.content.pm.PackageManager

/** App config values written to the manifest as `pyxpo.*` meta-data by `pyxpo build`. */
object PxAppConfig {
    fun meta(ctx: Context, key: String): String? = try {
        @Suppress("DEPRECATION")
        ctx.packageManager.getApplicationInfo(ctx.packageName, PackageManager.GET_META_DATA).metaData?.get(key)?.toString()
    } catch (e: Exception) { null }

    /** "argb:AARRGGBB" (a plain "#..." meta-data value would be parsed into an int by aapt). */
    fun color(ctx: Context, key: String): Int? = meta(ctx, key)?.removePrefix("argb:")?.let { h ->
        try { android.graphics.Color.parseColor("#$h") } catch (e: Exception) { null }
    }
}

/** In-app copy of the splash: stays up until the first batch is applied, or until `SplashScreen.hide()` after
 *  `SplashScreen.prevent_auto_hide()`. Debug builds honour the `pyxpo_splash_hold_ms` intent extra (screenshots, tests). */
class PxSplash(private val ctx: Context) {
    private var view: android.view.View? = null
    private var held = false
    private var first = true

    private fun res(name: String, type: String) = ctx.resources.getIdentifier(name, type, ctx.packageName)

    fun show(container: android.view.ViewGroup) {
        val v = android.widget.FrameLayout(ctx)
        val bg = res("pyxpo_splash_bg", "color")
        v.setBackgroundColor(if (bg != 0) ctx.resources.getColor(bg, null) else PxAppConfig.color(ctx, "pyxpo.background_color") ?: 0)
        val img = res("pyxpo_splash_image", "drawable")
        if (img != 0) {
            val iv = android.widget.ImageView(ctx)
            iv.setImageResource(img)
            iv.adjustViewBounds = true
            iv.scaleType = android.widget.ImageView.ScaleType.FIT_CENTER
            val w = (PxAppConfig.meta(ctx, "pyxpo.splash_image_width")?.toFloatOrNull() ?: 200f) * ctx.resources.displayMetrics.density
            v.addView(iv, android.widget.FrameLayout.LayoutParams(w.toInt(), android.view.ViewGroup.LayoutParams.WRAP_CONTENT, android.view.Gravity.CENTER))
        }
        v.isClickable = true  // swallow touches while it is up
        container.addView(v, android.view.ViewGroup.LayoutParams(-1, -1))
        view = v
    }

    fun preventAutoHide() { held = true }

    fun batchApplied() {
        if (!first) return
        first = false
        var holdMs = 0
        if (ctx.applicationInfo.flags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE != 0)
            holdMs = (ctx as? android.app.Activity)?.intent?.getIntExtra("pyxpo_splash_hold_ms", 0) ?: 0
        if (holdMs > 0) android.os.Handler(android.os.Looper.getMainLooper()).postDelayed({ hide() }, holdMs.toLong())
        else if (!held) hide()
    }

    fun hide() {
        val v = view ?: return
        view = null
        v.animate().alpha(0f).setDuration(250).withEndAction { (v.parent as? android.view.ViewGroup)?.removeView(v) }.start()
    }
}
