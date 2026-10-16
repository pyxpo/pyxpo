"""pyxpo-localization: expo-localization API from the startup constants, and the desktop fallback."""
import pytest

from pyxpo.module_testing import FakeBridge

import pyxpo_localization as Localization

EN = {
    "languageTag": "en-IN", "languageCode": "en", "regionCode": "IN", "languageRegionCode": "IN",
    "currencyCode": "INR", "currencySymbol": "₹", "decimalSeparator": ".", "digitGroupingSeparator": ",",
    "textDirection": "ltr", "measurementSystem": "metric", "temperatureUnit": "celsius",
}
AR = {"languageTag": "ar-EG", "languageCode": "ar", "textDirection": "rtl"}
CAL = {"calendar": "gregory", "timeZone": "Asia/Kolkata", "uses24hourClock": False, "firstWeekday": 1}


def test_desktop(monkeypatch):
    monkeypatch.setenv("LC_ALL", "de_DE.UTF-8")
    monkeypatch.setenv("TZ", "Europe/Berlin")
    loc = Localization.get_locales()
    assert len(loc) == 1
    assert (loc[0].language_tag, loc[0].language_code, loc[0].region_code) == ("de-DE", "de", "DE")
    assert (loc[0].measurement_system, loc[0].temperature_unit, loc[0].text_direction) == ("metric", "celsius", "ltr")
    assert loc[0].currency_code is None
    cal = Localization.getCalendars()[0]
    assert (cal.calendar, cal.time_zone) == ("gregory", "Europe/Berlin")


def test_desktop_script_and_posix(monkeypatch):
    monkeypatch.setenv("LC_ALL", "zh_Hant_TW")
    assert Localization.get_locales()[0].language_tag == "zh-Hant-TW"
    monkeypatch.setenv("LC_ALL", "C")
    loc = Localization.get_locales()[0]
    assert (loc.language_tag, loc.temperature_unit, loc.measurement_system) == ("en-US", "fahrenheit", "us")


def test_native_constants():
    with FakeBridge("ios", constants={"Localization": {"locales": [EN, AR], "calendars": [CAL]}}):
        locs = Localization.getLocales()
        assert [l.language_tag for l in locs] == ["en-IN", "ar-EG"]
        assert locs[0].currency_symbol == "₹" and locs[0]["digitGroupingSeparator"] == ","
        assert locs[1].text_direction == "rtl" and locs[1].region_code is None
        assert locs[0].to_dict()["languageTag"] == "en-IN"
        with pytest.raises(KeyError):
            locs[0]["nope"]
        cal = Localization.use_calendars()[0]
        assert cal.uses_24_hour_clock is False and cal["timeZone"] == "Asia/Kolkata" and cal.first_weekday == 1


def test_empty_constants_fall_back():
    with FakeBridge("android", constants={"Localization": {"locales": [], "calendars": []}}):
        assert Localization.get_locales()[0].language_tag == "en-US"
        assert Localization.get_calendars()[0].calendar == "gregory"


def test_not_linked():
    from pyxpo.module_api import ModuleNotLinkedError
    with FakeBridge("android"):
        with pytest.raises(ModuleNotLinkedError):
            Localization.get_locales()
