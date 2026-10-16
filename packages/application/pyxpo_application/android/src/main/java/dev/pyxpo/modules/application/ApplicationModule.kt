package dev.pyxpo.modules.application

import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.os.Build
import android.provider.Settings
import com.android.installreferrer.api.InstallReferrerClient
import com.android.installreferrer.api.InstallReferrerStateListener
import dev.pyxpo.moduleapi.PxModule
import dev.pyxpo.moduleapi.PxModuleContext
import dev.pyxpo.moduleapi.PxReply
import org.json.JSONArray

/** expo-application on Android: `PackageInfo`, `ANDROID_ID` and the Play install referrer. */
class ApplicationModule : PxModule() {
    override val name = "Application"

    private fun info(c: Context): PackageInfo =
        if (Build.VERSION.SDK_INT >= 33) c.packageManager.getPackageInfo(c.packageName, PackageManager.PackageInfoFlags.of(0))
        else @Suppress("DEPRECATION") c.packageManager.getPackageInfo(c.packageName, 0)

    @SuppressLint("HardwareIds")
    override fun constants(context: Context): Map<String, Any?> {
        val p = info(context)
        val build = if (Build.VERSION.SDK_INT >= 28) p.longVersionCode else @Suppress("DEPRECATION") p.versionCode.toLong()
        return mapOf(
            "applicationName" to context.applicationInfo.loadLabel(context.packageManager).toString(),
            "applicationId" to context.packageName,
            "nativeApplicationVersion" to p.versionName,
            "nativeBuildVersion" to build.toString(),
            "androidId" to Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID),
        )
    }

    override fun call(ctx: PxModuleContext, method: String, args: JSONArray, reply: PxReply) {
        val c = ctx.activity
        when (method) {
            "getInstallationTime" -> reply(info(c).firstInstallTime, null)
            "getLastUpdateTime" -> reply(info(c).lastUpdateTime, null)
            "getInstallReferrer" -> referrer(c, reply)
            else -> reply(null, "Application has no method '$method'")
        }
    }

    private fun referrer(c: Context, reply: PxReply) {
        val client = InstallReferrerClient.newBuilder(c.applicationContext).build()
        var done = false
        fun finish(value: Any?, error: String?) {
            if (done) return
            done = true
            try { client.endConnection() } catch (_: Exception) {}
            reply(value, error)
        }
        try {
            client.startConnection(object : InstallReferrerStateListener {
                override fun onInstallReferrerSetupFinished(code: Int) {
                    when (code) {
                        InstallReferrerClient.InstallReferrerResponse.OK ->
                            try { finish(client.installReferrer.installReferrer, null) }
                            catch (e: Exception) { finish(null, "install referrer failed: ${e.message}") }
                        InstallReferrerClient.InstallReferrerResponse.FEATURE_NOT_SUPPORTED ->
                            finish(null, "install referrer is not supported (no Google Play Store)")
                        InstallReferrerClient.InstallReferrerResponse.SERVICE_UNAVAILABLE ->
                            finish(null, "install referrer service is unavailable")
                        else -> finish(null, "install referrer failed with code $code")
                    }
                }

                override fun onInstallReferrerServiceDisconnected() {
                    finish(null, "install referrer service disconnected")
                }
            })
        } catch (e: Exception) {
            finish(null, "install referrer failed: ${e.message}")
        }
    }
}
