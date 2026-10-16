# pyxpo-localization

The user's languages, region formats and calendar settings for [pyxpo](https://github.com/pyxpo/pyxpo)
apps. The API follows [expo-localization](https://docs.expo.dev/versions/latest/sdk/localization/).

```sh
pip install pyxpo-localization
```

```toml
[tool.pyxpo]
modules = ["localization"]
```

```python
import pyxpo_localization as Localization

locale = Localization.get_locales()[0]
print(locale.language_tag, locale.region_code, locale.currency_code)   # en-IN IN INR
cal = Localization.get_calendars()[0]
print(cal.time_zone, cal.uses_24_hour_clock, cal.first_weekday)        # Asia/Kolkata False 1
```

Every name also has its expo-localization spelling (`Localization.getLocales`, `Localization.useCalendars`).
Records accept Expo's camelCase keys too: `locale["languageTag"]`, and `locale.to_dict()` gives the
camelCase dict.

The values are read once when the app starts. On the desktop they come from `LC_ALL` / `LC_MESSAGES` /
`LANG` and the system time zone, and the fields the desktop cannot tell (currency, separators) are `None`.

## Functions

| Function | Returns |
| --- | --- |
| `get_locales()` | `list[Locale]`, the preferred languages, most preferred first. Never empty. |
| `get_calendars()` | `list[Calendar]`, the user's calendars, preferred first. Never empty. |
| `use_locales()`, `use_calendars()` | The same, for use in components. |

## `Locale`

| Field | Example | Notes |
| --- | --- | --- |
| `language_tag` | `"en-IN"` | BCP 47 tag. |
| `language_code` | `"en"` | |
| `language_script_code` | `"Hant"` | `None` when the tag has no script. |
| `region_code` | `"IN"` | iOS: the region setting. Android: the locale's region. |
| `language_region_code` | `"IN"` | The region in the language tag. |
| `currency_code`, `currency_symbol` | `"INR"`, `"₹"` | iOS: from the region setting. |
| `language_currency_code`, `language_currency_symbol` | `"INR"`, `"₹"` | From the language tag's region. |
| `decimal_separator`, `digit_grouping_separator` | `"."`, `","` | |
| `text_direction` | `"ltr"` | `"ltr"` or `"rtl"`. |
| `measurement_system` | `"metric"` | `"metric"`, `"us"` or `"uk"`. |
| `temperature_unit` | `"celsius"` | `"celsius"` or `"fahrenheit"`. Follows the user's setting on iOS 16+ and Android 14+. |

## `Calendar`

| Field | Example | Notes |
| --- | --- | --- |
| `calendar` | `"gregory"` | CLDR name, as in JavaScript `Intl`. |
| `time_zone` | `"Asia/Kolkata"` | IANA id. |
| `uses_24_hour_clock` | `False` | |
| `first_weekday` | `1` | 1 is Sunday, 7 is Saturday. |

## Platforms

iOS 15+, Android 7 (API 24)+. No permissions.
