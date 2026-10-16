import Foundation

/// expo-localization on iOS. Language fields come from each preferred language; region, currency and
/// number formats come from the user's region setting (`Locale.current`), as in Settings.
final class LocalizationModule: PxModule {
    static let moduleName = "Localization"

    required init() {}

    static var constants: [String: Any] {
        ["locales": locales, "calendars": [calendar]]
    }

    private static func value(_ s: String?) -> Any { s ?? NSNull() }

    private static func measurementSystem(_ l: Locale) -> String {
        if #available(iOS 16, *) {
            switch l.measurementSystem {
            case .us: return "us"
            case .uk: return "uk"
            default: return "metric"
            }
        }
        return l.usesMetricSystem ? "metric" : "us"
    }

    /// The unit `MeasurementFormatter` picks for the locale (follows the Temperature setting on iOS 16+).
    private static func temperatureUnit(_ l: Locale) -> String {
        let f = MeasurementFormatter()
        f.locale = l
        f.numberFormatter.maximumFractionDigits = 0
        let text = f.string(from: Measurement(value: 0, unit: UnitTemperature.celsius))
        return text.contains("F") ? "fahrenheit" : "celsius"
    }

    private static var locales: [[String: Any]] {
        let current = Locale.current
        let tags = Locale.preferredLanguages.isEmpty ? [current.identifier] : Locale.preferredLanguages
        return tags.map { tag in
            let l = Locale(identifier: tag)
            let lang = l.languageCode
            return [
                "languageTag": tag,
                "languageCode": value(lang),
                "languageScriptCode": value(l.scriptCode),
                "regionCode": value(current.regionCode),
                "languageRegionCode": value(l.regionCode),
                "currencyCode": value(current.currencyCode),
                "currencySymbol": value(current.currencySymbol),
                "languageCurrencyCode": value(l.currencyCode),
                "languageCurrencySymbol": value(l.currencySymbol),
                "decimalSeparator": value(current.decimalSeparator),
                "digitGroupingSeparator": value(current.groupingSeparator),
                "textDirection": lang.map { Locale.characterDirection(forLanguage: $0) == .rightToLeft ? "rtl" : "ltr" } ?? NSNull(),
                "measurementSystem": measurementSystem(current),
                "temperatureUnit": temperatureUnit(current),
            ]
        }
    }

    /// CLDR names for the calendar identifiers, as on the web (`Intl`).
    private static func cldr(_ id: Calendar.Identifier) -> String {
        switch id {
        case .gregorian: return "gregory"
        case .buddhist: return "buddhist"
        case .chinese: return "chinese"
        case .coptic: return "coptic"
        case .ethiopicAmeteMihret: return "ethiopic"
        case .ethiopicAmeteAlem: return "ethioaa"
        case .hebrew: return "hebrew"
        case .indian: return "indian"
        case .islamic: return "islamic"
        case .islamicCivil: return "islamic-civil"
        case .islamicTabular: return "islamic-tbla"
        case .islamicUmmAlQura: return "islamic-umalqura"
        case .iso8601: return "iso8601"
        case .japanese: return "japanese"
        case .persian: return "persian"
        case .republicOfChina: return "roc"
        default: return "gregory"
        }
    }

    private static var calendar: [String: Any] {
        let cal = Calendar.current
        let hourFormat = DateFormatter.dateFormat(fromTemplate: "j", options: 0, locale: Locale.current) ?? ""
        return [
            "calendar": cldr(cal.identifier),
            "timeZone": TimeZone.current.identifier,
            "uses24hourClock": !hourFormat.contains("a"),
            "firstWeekday": cal.firstWeekday,
        ]
    }

    func call(_ ctx: PxModuleContext, _ method: String, _ args: [Any], _ reply: @escaping PxReply) {
        reply(nil, "Localization has no method '\(method)'")
    }
}
