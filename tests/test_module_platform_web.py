"""In the browser, modules use their web backends even while the dev tools emulate an iOS or Android device."""
from __future__ import annotations

import sys

from pyxpo import module_api, modules
from pyxpo.apis import _env


def test_browser_reports_web_while_emulating_ios(monkeypatch):
    monkeypatch.setattr(sys, "platform", "emscripten")
    monkeypatch.setitem(_env.current._data, "os", "ios")
    monkeypatch.setitem(_env.current._data, "modules", [])
    assert module_api.platform() == "web"
    modules.require_linked("Fetch", "fetch")  # no native modules in a browser: never "not linked"


def test_native_ios_still_reports_ios(monkeypatch):
    monkeypatch.setitem(_env.current._data, "os", "ios")
    assert module_api.platform() == "ios"
