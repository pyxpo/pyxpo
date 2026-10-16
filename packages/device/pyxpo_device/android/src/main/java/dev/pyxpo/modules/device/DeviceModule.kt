package dev.pyxpo.modules.device

import android.app.ActivityManager
import android.app.UiModeManager
import android.content.Context
import android.content.res.Configuration
import android.os.Build
import android.os.SystemClock
import android.provider.Settings
import dev.pyxpo.moduleapi.PxModule
import dev.pyxpo.moduleapi.PxModuleContext
import dev.pyxpo.moduleapi.PxReply
import org.json.JSONArray
import java.io.File

/** expo-device on Android. Constants come from `Build`, `ActivityManager` and the configuration at startup. */
class DeviceModule : PxModule() {
    override val name = "Device"

    override fun constants(context: Context): Map<String, Any?> {
        val mem = ActivityManager.MemoryInfo()
        (context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager).getMemoryInfo(mem)
        return mapOf(
            "isDevice" to !isEmulator(),
            "brand" to Build.BRAND,
            "manufacturer" to Build.MANUFACTURER,
            "modelName" to Build.MODEL,
            "modelId" to null,
            "designName" to Build.DEVICE,
            "productName" to Build.PRODUCT,
            "deviceYearClass" to null,
            "totalMemory" to mem.totalMem,
            "supportedCpuArchitectures" to Build.SUPPORTED_ABIS.toList(),
            "osName" to "Android",
            "osVersion" to Build.VERSION.RELEASE,
            "osBuildId" to Build.DISPLAY,
            "osInternalBuildId" to Build.ID,
            "osBuildFingerprint" to Build.FINGERPRINT,
            "platformApiLevel" to Build.VERSION.SDK_INT,
            "deviceName" to (Settings.Global.getString(context.contentResolver, Settings.Global.DEVICE_NAME) ?: Build.MODEL),
            "deviceType" to deviceType(context),
        )
    }

    private fun isEmulator(): Boolean =
        Build.FINGERPRINT.startsWith("generic") || Build.FINGERPRINT.contains("emulator") ||
            Build.HARDWARE == "goldfish" || Build.HARDWARE == "ranchu" ||
            Build.MODEL.contains("Emulator") || Build.MODEL.contains("Android SDK built for") ||
            Build.PRODUCT.startsWith("sdk") || Build.PRODUCT.contains("emulator") || Build.PRODUCT.contains("simulator")

    private fun deviceType(context: Context): Int {
        val ui = context.getSystemService(Context.UI_MODE_SERVICE) as? UiModeManager
        if (ui?.currentModeType == Configuration.UI_MODE_TYPE_TELEVISION) return 4
        val pm = context.packageManager
        if (pm.hasSystemFeature("android.software.leanback")) return 4
        if (pm.hasSystemFeature("org.chromium.arc") || pm.hasSystemFeature("org.chromium.arc.device_management")) return 3
        return if (context.resources.configuration.smallestScreenWidthDp >= 600) 2 else 1
    }

    private fun isRooted(): Boolean {
        if (Build.TAGS?.contains("test-keys") == true) return true
        val paths = listOf("/system/app/Superuser.apk", "/sbin/su", "/system/bin/su", "/system/xbin/su",
            "/data/local/xbin/su", "/data/local/bin/su", "/system/sd/xbin/su", "/system/bin/failsafe/su", "/data/local/su")
        return paths.any { File(it).exists() }
    }

    // Android 8+ throws unless the app declares REQUEST_INSTALL_PACKAGES; without it the answer is false.
    private fun sideLoading(c: Context): Boolean =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            try { c.packageManager.canRequestPackageInstalls() } catch (e: SecurityException) { false }
        } else {
            @Suppress("DEPRECATION")
            Settings.Secure.getInt(c.contentResolver, Settings.Secure.INSTALL_NON_MARKET_APPS, 0) == 1
        }

    override fun call(ctx: PxModuleContext, method: String, args: JSONArray, reply: PxReply) {
        val c = ctx.activity
        when (method) {
            "getUptime" -> reply(SystemClock.uptimeMillis(), null)
            "getMaxMemory" -> {
                val max = Runtime.getRuntime().maxMemory()
                reply(if (max == Long.MAX_VALUE) 9007199254740991L else max, null)
            }
            "isRooted" -> reply(isRooted(), null)
            "isSideLoadingEnabled" -> reply(sideLoading(c), null)
            "getPlatformFeatures" -> reply(c.packageManager.systemAvailableFeatures.mapNotNull { it.name }, null)
            "hasPlatformFeature" -> reply(c.packageManager.hasSystemFeature(args.optString(0)), null)
            else -> reply(null, "Device has no method '$method'")
        }
    }
}
