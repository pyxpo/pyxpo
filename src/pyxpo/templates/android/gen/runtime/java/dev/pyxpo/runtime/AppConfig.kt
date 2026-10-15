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
