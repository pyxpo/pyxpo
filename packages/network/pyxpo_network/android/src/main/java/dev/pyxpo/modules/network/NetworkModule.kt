package dev.pyxpo.modules.network

import android.content.Context
import android.net.ConnectivityManager
import android.net.LinkProperties
import android.net.Network
import android.net.NetworkCapabilities
import android.provider.Settings
import dev.pyxpo.moduleapi.PxModule
import dev.pyxpo.moduleapi.PxModuleContext
import dev.pyxpo.moduleapi.PxReply
import org.json.JSONArray
import java.net.Inet4Address
import java.net.NetworkInterface

/** expo-network on Android: `ConnectivityManager` state, the default network callback and airplane mode. */
class NetworkModule : PxModule() {
    override val name = "Network"

    private var callback: ConnectivityManager.NetworkCallback? = null

    private fun cm(c: Context) = c.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager

    private fun state(caps: NetworkCapabilities?): Map<String, Any?> {
        if (caps == null) return mapOf("type" to "NONE", "isConnected" to false, "isInternetReachable" to false)
        val type = when {
            caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN) -> "VPN"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "WIFI"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "CELLULAR"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "ETHERNET"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_BLUETOOTH) -> "BLUETOOTH"
            else -> "UNKNOWN"
        }
        return mapOf(
            "type" to type,
            "isConnected" to caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET),
            "isInternetReachable" to caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED),
        )
    }

    private fun current(c: Context): Map<String, Any?> {
        val m = cm(c)
        return state(m.activeNetwork?.let { m.getNetworkCapabilities(it) })
    }

    private fun ipAddress(c: Context): String {
        val m = cm(c)
        m.activeNetwork?.let { m.getLinkProperties(it) }?.linkAddresses
            ?.map { it.address }?.firstOrNull { it is Inet4Address && !it.isLoopbackAddress }
            ?.let { return it.hostAddress ?: "0.0.0.0" }
        return try {
            NetworkInterface.getNetworkInterfaces().toList().filter { it.isUp && !it.isLoopback }
                .flatMap { it.inetAddresses.toList() }.firstOrNull { it is Inet4Address }?.hostAddress ?: "0.0.0.0"
        } catch (_: Exception) { "0.0.0.0" }
    }

    override fun call(ctx: PxModuleContext, method: String, args: JSONArray, reply: PxReply) {
        val c = ctx.activity.applicationContext
        when (method) {
            "getState" -> reply(current(c), null)
            "getIpAddress" -> reply(ipAddress(c), null)
            "isAirplaneModeEnabled" -> reply(Settings.Global.getInt(c.contentResolver, Settings.Global.AIRPLANE_MODE_ON, 0) != 0, null)
            "startObserving" -> { start(ctx, c); reply(null, null) }
            "stopObserving" -> { stop(c); reply(null, null) }
            else -> reply(null, "Network has no method '$method'")
        }
    }

    /** The default-network callback reports the current network right after it is registered. */
    private fun start(ctx: PxModuleContext, c: Context) {
        if (callback != null) {
            ctx.emit("Network.state", current(c))
            return
        }
        val cb = object : ConnectivityManager.NetworkCallback() {
            override fun onCapabilitiesChanged(network: Network, caps: NetworkCapabilities) {
                ctx.emit("Network.state", state(caps))
            }
            override fun onLost(network: Network) {
                ctx.emit("Network.state", state(null))
            }
            override fun onUnavailable() {
                ctx.emit("Network.state", state(null))
            }
        }
        callback = cb
        try {
            cm(c).registerDefaultNetworkCallback(cb)
        } catch (e: Exception) {
            callback = null
            ctx.emit("Network.state", current(c))
        }
    }

    private fun stop(c: Context) {
        val cb = callback ?: return
        callback = null
        try { cm(c).unregisterNetworkCallback(cb) } catch (_: Exception) {}
    }
}
