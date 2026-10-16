package dev.pyxpo.modules.localization

import android.content.Context
import android.os.Build
import android.os.LocaleList
import android.text.TextUtils
import android.text.format.DateFormat
import android.util.LayoutDirection
import dev.pyxpo.moduleapi.PxModule
import dev.pyxpo.moduleapi.PxModuleContext
import dev.pyxpo.moduleapi.PxReply
import org.json.JSONArray
import java.text.DecimalFormatSymbols
import java.util.Currency
import java.util.Locale
import java.util.TimeZone

/** expo-localization on Android: `LocaleList`, `DecimalFormatSymbols`, `Currency` and the ICU calendar. */
class LocalizationModule : PxModule() {
    override val name = "Localization"

    override fun constants(context: Context): Map<String, Any?> =
        mapOf("locales" to locales(), "calendars" to listOf(calendar(context)))

    private fun currency(l: Locale): Currency? = try { Currency.getInstance(l) } catch (_: Exception) { null }

    private fun measurementSystem(l: Locale): String? {
        if (l.country.isEmpty()) return null
        if (Build.VERSION.SDK_INT >= 28) {
            return when (android.icu.util.LocaleData.getMeasurementSystem(android.icu.util.ULocale.forLocale(l))) {
                android.icu.util.LocaleData.MeasurementSystem.US -> "us"
                android.icu.util.LocaleData.MeasurementSystem.UK -> "uk"
                else -> "metric"
            }
        }
        return when (l.country) { "US", "LR", "MM" -> "us"; "GB" -> "uk"; else -> "metric" }
    }

    /** Android 14+ lets the user pick the unit (`-u-mu-` locale extension); else the region's CLDR default. */
    private fun temperatureUnit(l: Locale): String? {
        when (l.getUnicodeLocaleType("mu")) {
            "celsius" -> return "celsius"
            "fahrenhe" -> return "fahrenheit"
        }
        if (l.country.isEmpty()) return null
        return when (l.country) { "US", "BS", "BZ", "KY", "PR", "PW", "LR", "FM", "MH" -> "fahrenheit"; else -> "celsius" }
    }

    private fun locales(): List<Map<String, Any?>> {
        val list = LocaleList.getDefault()
        return (0 until list.size()).map { i ->
            val l = list[i]
            val cur = currency(l)
            val sym = DecimalFormatSymbols.getInstance(l)
            val region = l.country.ifEmpty { null }
            mapOf(
                "languageTag" to l.toLanguageTag(),
                "languageCode" to l.language.ifEmpty { null },
                "languageScriptCode" to l.script.ifEmpty { null },
                "regionCode" to region,
                "languageRegionCode" to region,
                "currencyCode" to cur?.currencyCode,
                "currencySymbol" to cur?.getSymbol(l),
                "languageCurrencyCode" to cur?.currencyCode,
                "languageCurrencySymbol" to cur?.getSymbol(l),
                "decimalSeparator" to sym.decimalSeparator.toString(),
                "digitGroupingSeparator" to sym.groupingSeparator.toString(),
                "textDirection" to if (TextUtils.getLayoutDirectionFromLocale(l) == LayoutDirection.RTL) "rtl" else "ltr",
                "measurementSystem" to measurementSystem(l),
                "temperatureUnit" to temperatureUnit(l),
            )
        }
    }

    private fun calendar(c: Context): Map<String, Any?> {
        val cal = android.icu.util.Calendar.getInstance()
        val type = cal.type.let { if (it == "gregorian") "gregory" else it }
        return mapOf(
            "calendar" to type,
            "timeZone" to TimeZone.getDefault().id,
            "uses24hourClock" to DateFormat.is24HourFormat(c),
            "firstWeekday" to cal.firstDayOfWeek,
        )
    }

    override fun call(ctx: PxModuleContext, method: String, args: JSONArray, reply: PxReply) {
        reply(null, "Localization has no method '$method'")
    }
}
