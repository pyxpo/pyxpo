# pyxpo-localization

The user's languages, region formats and calendar settings for [pyxpo](https://github.com/pyxpo/pyxpo) apps, written
in Python: preferred languages, currency, number separators, text direction, units, time zone, 12 or 24 hour clock and
first day of the week. The names follow
[expo-localization](https://docs.expo.dev/versions/latest/sdk/localization/), in Python style.

<p align="center">
  <img src="https://raw.githubusercontent.com/pyxpo/pyxpo/main/packages/localization/docs/images/hero.png" width="820" alt="The localization module on Android and iOS: language tag, region, currency, separators and the calendar">
</p>

```python
import pyxpo_localization as Localization

locale = Localization.get_locales()[0]
print(locale.language_tag, locale.region_code, locale.currency_code)   # "en-IN", "IN", "INR"
print(Localization.get_calendars()[0].time_zone)                        # "Asia/Kolkata"
```

## Features

- **Locales:** the user's preferred languages in order, each with its region, currency, separators, text
  direction, measurement system and temperature unit.
- **Calendars:** calendar type, IANA time zone, 24 hour clock and first weekday.
- **Never empty:** both lists always have at least one entry, so `[0]` is safe.
- **Plain records:** frozen dataclasses with snake_case fields, Expo's camelCase keys through `locale["languageTag"]`,
  and `to_dict()`.
- **Hooks:** `use_locales()` and `use_calendars()` for components.
- **Desktop fallback:** the desktop reads `LC_ALL`, `LC_MESSAGES`, `LANG` and the system time zone. Fields it cannot
  tell are `None`.
- **No permissions**, no config plugin, no dependencies.
- **Typed:** ships `py.typed`. Every name also has its expo spelling (`Localization.getLocales`).

## Contents

| If you are... | Start here |
| --- | --- |
| Picking the app's language | [Quick start](#quick-start) → [Locales](#locales) |
| Formatting money or numbers | [Currency and numbers](#currency-and-numbers) |
| Showing times in the user's style | [Calendars](#calendars) |
| Supporting right-to-left languages | [Text direction](#text-direction) |
| Looking for exact signatures | [API reference](#api-reference) · [Errors](#errors) |
| Seeing it in a real app | [Recipe: a price and a date in the user's style](#recipe-a-price-and-a-date-in-the-users-style) |
| Stuck | [Testing](#testing) · [Troubleshooting](#troubleshooting) · [FAQ](#faq) |

## Platform support

| Target | What works |
| --- | --- |
| Android, API 24+ | Everything. Temperature unit follows the user's setting on Android 14+. |
| iOS 15+ | Everything. Temperature unit follows the user's setting on iOS 16+. |
| Web page and desktop window (`pyxpo run web` / `pyxpo run desktop`) | Language and region from the environment (`LANG`), time zone from the system. Currency, separators and the 24 hour flag are `None`. |

Requires Python 3.9+ and `pyxpo>=0.1.0a2`.

## Install

```sh
pip install pyxpo-localization
```

Add the module to your app's `pyproject.toml`:

```toml
[tool.pyxpo]
modules = ["localization"]
```

The module has native code, so rebuild the app after adding it (`pyxpo run android` or `pyxpo run ios`). It needs no
permission and adds no library.

## Quick start

```python
import pyxpo_localization as Localization
from pyxpo import Text, View, component


@component
def Settings():
    locale = Localization.use_locales()[0]
    cal = Localization.use_calendars()[0]
    return View(
        Text("Language: %s" % locale.language_tag),
        Text("Region: %s" % (locale.region_code or "unknown")),
        Text("Currency: %s %s" % (locale.currency_code or "?", locale.currency_symbol or "")),
        Text("Time zone: %s" % (cal.time_zone or "unknown")),
        Text("Clock: %s" % ("24 hour" if cal.uses_24_hour_clock else "12 hour")),
    )
```

> **Tip:** the values are read once when the app starts. If the user changes the language in Settings, the app
> sees the new value after a restart, not while it runs. Do not poll for a change.

## Locales

`get_locales()` returns the preferred languages, most preferred first. Use the first one for the user's formatting
and the whole list when you choose a translation.

```python
locales = Localization.get_locales()
for locale in locales:
    print(locale.language_tag)                   # "en-IN", "hi-IN"

supported = {"en", "hi", "de"}
language = next((l.language_code for l in locales if l.language_code in supported), "en")
```

| Field | Example | Notes |
| --- | --- | --- |
| `language_tag` | `"en-IN"` | BCP 47 tag. Always set. |
| `language_code` | `"en"` | |
| `language_script_code` | `"Hant"` | `None` when the tag has no script. |
| `region_code` | `"IN"` | The region setting on iOS, the locale's region on Android. |
| `language_region_code` | `"IN"` | The region inside the language tag. |

<p align="center">
  <img src="https://raw.githubusercontent.com/pyxpo/pyxpo/main/packages/localization/docs/images/locale.png" width="720" alt="The locale fields on Android and iOS">
</p>

The two screenshots come from two devices with different settings (an iPhone set to English, India and an Android
emulator set to English, United States), which is why the values differ. Both read the same fields.

## Currency and numbers

| Field | Example | Notes |
| --- | --- | --- |
| `currency_code`, `currency_symbol` | `"INR"`, `"₹"` | On iOS from the region setting. |
| `language_currency_code`, `language_currency_symbol` | `"INR"`, `"₹"` | From the region of the language tag. |
| `decimal_separator` | `"."` | |
| `digit_grouping_separator` | `","` | |
| `measurement_system` | `"metric"` | `"metric"`, `"us"` or `"uk"`. |
| `temperature_unit` | `"celsius"` | `"celsius"` or `"fahrenheit"`. |

These are the user's formats, not a currency conversion. The module does not know prices.

## Text direction

```python
rtl = Localization.get_locales()[0].text_direction == "rtl"
```

`text_direction` is `"ltr"` or `"rtl"`. Use it to mirror an icon or an alignment you set by hand.

## Calendars

```python
cal = Localization.get_calendars()[0]
print(cal.calendar, cal.time_zone, cal.uses_24_hour_clock, cal.first_weekday)
```

| Field | Example | Notes |
| --- | --- | --- |
| `calendar` | `"gregory"` | CLDR name, as in JavaScript `Intl`. |
| `time_zone` | `"Asia/Kolkata"` | IANA id. |
| `uses_24_hour_clock` | `False` | |
| `first_weekday` | `1` | 1 is Sunday, 7 is Saturday. |

## Errors

| Error | When | What to do |
| --- | --- | --- |
| `ModuleNotLinkedError` (from `pyxpo.module_api`) | The app was built without `"localization"` in `modules`. | Add it and rebuild. |
| `KeyError` from `locale["x"]` | A key that is not an Expo field name. | Use a field from the tables above. |

Nothing else is raised. A field the platform cannot tell is `None`.

## Config

There are no module options and no config plugin. The only setup is the `modules` entry.

## Web and desktop

The desktop host has no phone settings, so the values are guessed from the environment:

| Field | Desktop value |
| --- | --- |
| `language_tag`, `language_code`, `region_code` | From `LC_ALL`, `LC_MESSAGES` or `LANG` (`en_US.UTF-8` becomes `en-US`). `en-US` when unset or `C`. |
| `text_direction` | `"rtl"` for Arabic, Hebrew, Persian, Urdu and a few more, else `"ltr"`. |
| `measurement_system`, `temperature_unit` | From the region. `None` without one. |
| `time_zone` | `TZ`, or the `/etc/localtime` link, else the Python time zone name. |
| `calendar` | `"gregory"` |
| everything else | `None` |

## Recipe: a price and a date in the user's style

```python
from datetime import datetime

import pyxpo_localization as Localization


def format_price(amount: float) -> str:
    locale = Localization.get_locales()[0]
    dec = locale.decimal_separator or "."
    grp = locale.digit_grouping_separator or ","
    whole, frac = ("%.2f" % amount).split(".")
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    groups.insert(0, whole)
    return "%s%s%s%s" % (locale.currency_symbol or "", grp.join(groups), dec, frac)


def format_time(moment: datetime) -> str:
    cal = Localization.get_calendars()[0]
    return moment.strftime("%H:%M") if cal.uses_24_hour_clock else moment.strftime("%I:%M %p")
```

This groups in threes. A region that groups differently (for example 12,34,567 in India) needs a real number
formatting library on top.

## Production checklist

- [ ] The app falls back to a default language when none of `get_locales()` is translated.
- [ ] Code reads `locales[0]` and `calendars[0]` and never assumes a non-`None` currency, separator or clock flag.
- [ ] Right-to-left languages are tried at least once on a phone.
- [ ] A time zone is shown with the time when the user may travel.
- [ ] You handle `None` on the desktop and web builds.

## Testing

The lists come from the native side through `pyxpo.module_api`. In a unit test, patch the two getters, or build the
records yourself:

```python
import pyxpo_localization as Localization


def test_price_uses_the_user_symbol(monkeypatch):
    fake = Localization.Locale(language_tag="de-DE", currency_symbol="€",
                               decimal_separator=",", digit_grouping_separator=".")
    monkeypatch.setattr(Localization, "get_locales", lambda: [fake])
    assert Localization.get_locales()[0].currency_symbol == "€"
```

On the desktop test host, set `LANG` with `monkeypatch.setenv("LANG", "de_DE.UTF-8")` and `get_locales()` follows it.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `currency_code` is `None` | You are on the desktop, or the device has no region currency. Fall back to a default. |
| The language does not change after the user switches it | Values are read at startup. Restart the app. |
| `region_code` differs from the language region | The region setting and the language are separate. `language_region_code` is the language's own region. |
| `uses_24_hour_clock` is `None` | Desktop. Assume the locale default. |
| `ModuleNotLinkedError` | Add `"localization"` to `modules` and rebuild. |

## FAQ

**Is it the same as the web `navigator.language`?** It is the phone's list of preferred languages, which is the
nearest equivalent.

**Does it translate text?** No. It tells you what the user prefers. Keep your own translation tables.

**Why `first_weekday` 1 for Sunday?** It follows `Calendar.firstWeekday` on both platforms, as expo-localization does.

**Can I get the list in camelCase?** Each record has `to_dict()`, and `locale["languageTag"]` works.

## API reference

### Functions

| Function (expo name) | Returns |
| --- | --- |
| `get_locales()` (`getLocales`) | `list[Locale]`, never empty |
| `get_calendars()` (`getCalendars`) | `list[Calendar]`, never empty |
| `use_locales()` (`useLocales`) | `list[Locale]` for a component |
| `use_calendars()` (`useCalendars`) | `list[Calendar]` for a component |

### Types

| Name | Fields |
| --- | --- |
| `Locale` | `language_tag`, `language_code`, `language_script_code`, `region_code`, `language_region_code`, `currency_code`, `currency_symbol`, `language_currency_code`, `language_currency_symbol`, `decimal_separator`, `digit_grouping_separator`, `text_direction`, `measurement_system`, `temperature_unit`. Plus `to_dict()` and `locale["camelKey"]`. |
| `Calendar` | `calendar`, `time_zone`, `uses_24_hour_clock`, `first_weekday`. Plus `to_dict()` and `cal["camelKey"]`, where the key for the clock flag is `uses24hourClock`. |

## License

MIT
