"""The device's language, region and calendar settings: the expo-localization API.

    import pyxpo_localization as Localization

    locale = Localization.get_locales()[0]          # or Localization.getLocales()
    locale.language_code, locale.region_code         # "en", "US"
    locale["languageTag"]                            # camelCase keys work too: "en-US"
    cal = Localization.get_calendars()[0]
    cal.time_zone, cal.uses_24_hour_clock            # "Europe/Berlin", True

The values are read once when the app starts. On the desktop they come from the `LANG`/`LC_*` environment
and the system time zone; fields the desktop cannot tell are None.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, fields
from typing import Any, Dict, List, Optional

from pyxpo.module_api import constants, platform, require_linked

__version__ = "0.1.0a1"


class _Record:
    """Attribute access in snake_case, item access in Expo's camelCase."""
    _CAMEL: Dict[str, str] = {}

    def __getitem__(self, key: str) -> Any:
        name = self._CAMEL.get(key, key)
        if name not in {f.name for f in fields(self)}:  # type: ignore[arg-type]
            raise KeyError(key)
        return getattr(self, name)

    def to_dict(self) -> Dict[str, Any]:
        """The record with Expo's camelCase keys."""
        return {camel: getattr(self, snake) for camel, snake in self._CAMEL.items()}


@dataclass(frozen=True)
class Locale(_Record):
    """One preferred language, with the formatting rules of the user's region."""
    language_tag: str
    language_code: Optional[str] = None
    language_script_code: Optional[str] = None
    region_code: Optional[str] = None
    language_region_code: Optional[str] = None
    currency_code: Optional[str] = None
    currency_symbol: Optional[str] = None
    language_currency_code: Optional[str] = None
    language_currency_symbol: Optional[str] = None
    decimal_separator: Optional[str] = None
    digit_grouping_separator: Optional[str] = None
    text_direction: Optional[str] = None
    measurement_system: Optional[str] = None
    temperature_unit: Optional[str] = None


@dataclass(frozen=True)
class Calendar(_Record):
    """One calendar the user has set: its type, time zone, clock style and first weekday."""
    calendar: Optional[str] = None
    time_zone: Optional[str] = None
    uses_24_hour_clock: Optional[bool] = None
    first_weekday: Optional[int] = None


Locale._CAMEL = {
    "languageTag": "language_tag", "languageCode": "language_code", "languageScriptCode": "language_script_code",
    "regionCode": "region_code", "languageRegionCode": "language_region_code", "currencyCode": "currency_code",
    "currencySymbol": "currency_symbol", "languageCurrencyCode": "language_currency_code",
    "languageCurrencySymbol": "language_currency_symbol", "decimalSeparator": "decimal_separator",
    "digitGroupingSeparator": "digit_grouping_separator", "textDirection": "text_direction",
    "measurementSystem": "measurement_system", "temperatureUnit": "temperature_unit",
}
Calendar._CAMEL = {
    "calendar": "calendar", "timeZone": "time_zone", "uses24hourClock": "uses_24_hour_clock",
    "firstWeekday": "first_weekday",
}

# Regions that use Fahrenheit and US units (CLDR). The desktop has no other source for these.
_FAHRENHEIT = {"US", "BS", "BZ", "KY", "PR", "PW", "LR", "FM", "MH"}
_US_UNITS = {"US", "LR", "MM"}
_RTL = {"ar", "arc", "ckb", "dv", "fa", "ha", "he", "iw", "khw", "ks", "ku", "ps", "sd", "ur", "yi"}


def _from_native(cls: Any, raw: Dict[str, Any]) -> Any:
    return cls(**{snake: raw.get(camel) for camel, snake in cls._CAMEL.items()})


def _native(key: str) -> Optional[List[Dict[str, Any]]]:
    if platform() == "desktop":
        return None
    require_linked("Localization", "localization", package="pyxpo-localization")
    return list(constants("Localization").get(key) or [])


def _desktop_locale() -> Locale:
    raw = ""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        raw = os.environ.get(var, "")
        if raw:
            break
    raw = raw.split(".")[0].split("@")[0]
    if not raw or raw in ("C", "POSIX"):
        raw = "en_US"
    parts = raw.replace("-", "_").split("_")
    lang = parts[0].lower()
    script = next((p.title() for p in parts[1:] if len(p) == 4), None)
    region = next((p.upper() for p in parts[1:] if (len(p) == 2 and p.isalpha()) or (len(p) == 3 and p.isdigit())), None)
    tag = "-".join(p for p in (lang, script, region) if p)
    return Locale(
        language_tag=tag, language_code=lang, language_script_code=script, region_code=region,
        language_region_code=region, text_direction="rtl" if lang in _RTL else "ltr",
        measurement_system=None if region is None else "us" if region in _US_UNITS else "uk" if region == "GB" else "metric",
        temperature_unit=None if region is None else "fahrenheit" if region in _FAHRENHEIT else "celsius",
    )


def _desktop_time_zone() -> Optional[str]:
    tz = os.environ.get("TZ", "").lstrip(":")
    if "/" in tz and not tz.startswith("/"):
        return tz
    try:
        target = os.path.realpath("/etc/localtime")
    except OSError:
        return None
    marker = "zoneinfo/"
    return target.split(marker, 1)[1] if marker in target else (time.tzname[0] or None)


def get_locales() -> List[Locale]:
    """The user's preferred languages, most preferred first. Always at least one entry."""
    raw = _native("locales")
    if raw is None:
        return [_desktop_locale()]
    out = [_from_native(Locale, r) for r in raw]
    return out or [Locale(language_tag="en-US", language_code="en", region_code="US", language_region_code="US")]


def get_calendars() -> List[Calendar]:
    """The user's calendars, preferred first. Always at least one entry."""
    raw = _native("calendars")
    if raw is None:
        return [Calendar(calendar="gregory", time_zone=_desktop_time_zone())]
    out = [_from_native(Calendar, r) for r in raw]
    return out or [Calendar(calendar="gregory")]


def use_locales() -> List[Locale]:
    """Hook form of `get_locales()`. The values do not change while the app runs."""
    return get_locales()


def use_calendars() -> List[Calendar]:
    """Hook form of `get_calendars()`. The values do not change while the app runs."""
    return get_calendars()


getLocales = get_locales
getCalendars = get_calendars
useLocales = use_locales
useCalendars = use_calendars

__all__ = [
    "Locale", "Calendar", "get_locales", "get_calendars", "use_locales", "use_calendars",
    "getLocales", "getCalendars", "useLocales", "useCalendars",
]
