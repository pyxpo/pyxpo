package dev.pyxpo.modules.webbrowser

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import androidx.browser.customtabs.CustomTabColorSchemeParams
import androidx.browser.customtabs.CustomTabsClient
import androidx.browser.customtabs.CustomTabsIntent
import androidx.browser.customtabs.CustomTabsService
import androidx.browser.customtabs.CustomTabsServiceConnection
import androidx.browser.customtabs.CustomTabsSession
import dev.pyxpo.moduleapi.PxModule
import dev.pyxpo.moduleapi.PxModuleContext
import dev.pyxpo.moduleapi.PxReply
import org.json.JSONArray
import org.json.JSONObject

/** In-app browser on Custom Tabs, plus warm-up of the browser's Custom Tabs service. */
class WebBrowserModule : PxModule() {
    override val name = "WebBrowser"

    private var connection: Connection? = null

    override fun call(ctx: PxModuleContext, method: String, args: JSONArray, reply: PxReply) {
        when (method) {
            "open" -> open(ctx, args.optString(0), args.optJSONObject(1) ?: JSONObject(), reply)
            "dismiss" -> {
                // Brings the app's activity back over the tab; with createTask off, CLEAR_TOP also closes the tab.
                val a = ctx.activity
                a.startActivity(Intent(a, a.javaClass).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP))
                reply(mapOf("type" to "dismiss"), null)
            }
            "warmUp" -> withService(ctx, args.optString(0)) { c, pkg ->
                c.client?.warmup(0)
                reply(mapOf("servicePackage" to pkg), null)
            }
            "mayInitWithUrl" -> withService(ctx, args.optString(1)) { c, pkg ->
                c.session()?.mayLaunchUrl(Uri.parse(args.optString(0)), null, null)
                reply(mapOf("servicePackage" to pkg), null)
            }
            "coolDown" -> {
                val c = connection
                val want = args.optString(0)
                if (c == null || (want.isNotEmpty() && want != c.pkg)) { reply(emptyMap<String, Any?>(), null); return }
                try { ctx.activity.applicationContext.unbindService(c) } catch (_: IllegalArgumentException) {}
                connection = null
                reply(mapOf("servicePackage" to c.pkg), null)
            }
            "browsers" -> reply(browsers(ctx.activity), null)
            else -> reply(null, "unknown native call WebBrowser.$method")
        }
    }

    private fun open(ctx: PxModuleContext, url: String, o: JSONObject, reply: PxReply) {
        val a = ctx.activity
        val colors = CustomTabColorSchemeParams.Builder()
        if (o.has("toolbarColor") && !o.isNull("toolbarColor")) colors.setToolbarColor(o.getLong("toolbarColor").toInt())
        if (o.has("secondaryToolbarColor") && !o.isNull("secondaryToolbarColor"))
            colors.setSecondaryToolbarColor(o.getLong("secondaryToolbarColor").toInt())
        val builder = CustomTabsIntent.Builder(connection?.session())
            .setDefaultColorSchemeParams(colors.build())
            .setShowTitle(o.optBoolean("showTitle", false))
            .setUrlBarHidingEnabled(o.optBoolean("enableBarCollapsing", false))
            .setShareState(if (o.optBoolean("enableDefaultShareMenuItem", false)) CustomTabsIntent.SHARE_STATE_ON
                           else CustomTabsIntent.SHARE_STATE_OFF)
        val intent = builder.build().intent
        intent.data = Uri.parse(url)
        val pkg = o.optString("browserPackage").ifEmpty { CustomTabsClient.getPackageName(a, null) }
        if (!pkg.isNullOrEmpty()) intent.setPackage(pkg)
        if (o.optBoolean("createTask", true)) {
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            if (!o.optBoolean("showInRecents", false))
                intent.addFlags(Intent.FLAG_ACTIVITY_EXCLUDE_FROM_RECENTS or Intent.FLAG_ACTIVITY_NO_HISTORY)
        }
        if (intent.resolveActivity(a.packageManager) == null) {
            reply(null, "no browser on this device can open $url"); return
        }
        try {
            a.startActivity(intent)
            reply(mapOf("type" to "opened"), null)
        } catch (e: Throwable) {
            reply(null, e.message ?: e.toString())
        }
    }

    /** Binds the Custom Tabs service of `requested` (or the preferred browser) once, then runs `then`. */
    private fun withService(ctx: PxModuleContext, requested: String, then: (Connection, String) -> Unit) {
        val app = ctx.activity.applicationContext
        val pkg = requested.ifEmpty { CustomTabsClient.getPackageName(app, null) ?: "" }
        if (pkg.isEmpty()) { then(Connection(""), ""); return }
        val current = connection
        if (current != null && current.pkg == pkg && current.client != null) { then(current, pkg); return }
        if (current != null) {
            try { app.unbindService(current) } catch (_: IllegalArgumentException) {}
        }
        val c = Connection(pkg)
        connection = c
        c.onReady = { then(c, pkg) }
        if (!CustomTabsClient.bindCustomTabsService(app, pkg, c)) {
            connection = null
            then(Connection(""), "")
        }
    }

    private fun browsers(context: Context): Map<String, Any?> {
        val pm = context.packageManager
        val view = Intent(Intent.ACTION_VIEW, Uri.parse("https://example.com")).addCategory(Intent.CATEGORY_BROWSABLE)
        val browsers = pm.queryIntentActivities(view, PackageManager.MATCH_ALL).map { it.activityInfo.packageName }.distinct()
        val services = pm.queryIntentServices(Intent(CustomTabsService.ACTION_CUSTOM_TABS_CONNECTION), 0)
            .map { it.serviceInfo.packageName }.distinct()
        val default = pm.resolveActivity(view, PackageManager.MATCH_DEFAULT_ONLY)?.activityInfo?.packageName
            ?.takeIf { it != "android" }
        return mapOf(
            "browserPackages" to browsers,
            "servicePackages" to services,
            "defaultBrowserPackage" to default,
            "preferredBrowserPackage" to CustomTabsClient.getPackageName(context, null),
        )
    }

    private class Connection(val pkg: String) : CustomTabsServiceConnection() {
        var client: CustomTabsClient? = null
        var onReady: (() -> Unit)? = null
        private var session: CustomTabsSession? = null

        fun session(): CustomTabsSession? {
            if (session == null) session = client?.newSession(null)
            return session
        }

        override fun onCustomTabsServiceConnected(name: ComponentName, client: CustomTabsClient) {
            this.client = client
            onReady?.invoke()
            onReady = null
        }

        override fun onServiceDisconnected(name: ComponentName?) {
            client = null
            session = null
        }
    }
}
