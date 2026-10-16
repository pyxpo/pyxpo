"""pyxpo-web-browser: the expo-web-browser API, its options and the Android sign-in flow."""
import asyncio

import pytest

from pyxpo.apis import _events
from pyxpo.module_api import NotSupportedError
from pyxpo.module_testing import FakeBridge

import pyxpo_web_browser as WebBrowser


def run(coro):
    return asyncio.run(coro)


def test_desktop(monkeypatch):
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda u: opened.append(u) or True)
    assert run(WebBrowser.open_browser_async("https://pyxpo.dev")) == {"type": "opened"}
    assert opened == ["https://pyxpo.dev"]
    assert run(WebBrowser.dismiss_browser()) == {"type": "dismiss"}
    with pytest.raises(NotSupportedError):
        run(WebBrowser.open_auth_session_async("https://a.example/auth", "app://cb"))
    assert run(WebBrowser.warm_up_async()) == {}
    assert run(WebBrowser.get_custom_tabs_supporting_browsers_async())["browserPackages"] == []
    assert WebBrowser.maybe_complete_auth_session()["type"] == "failed"


def test_bad_arguments():
    with pytest.raises(ValueError):
        run(WebBrowser.open_browser_async("file:///etc/passwd"))
    with pytest.raises(ValueError):
        run(WebBrowser.open_browser_async(""))
    with pytest.raises(ValueError):
        run(WebBrowser.open_browser_async("https://x.example", dismiss_button_style="back"))
    with pytest.raises(ValueError):
        run(WebBrowser.open_browser_async("https://x.example", presentation_style="sideways"))


def test_ios_open_options_and_lock():
    with FakeBridge("ios") as fb:
        gate = {}

        def opener(url, opts):
            gate["opts"] = opts
            return {"type": "cancel"}
        fb.on("WebBrowser", "open", opener)
        res = run(WebBrowser.openBrowserAsync("https://pyxpo.dev", toolbarColor="#ff0000", controls_color="white",
                                               dismiss_button_style="close", presentation_style="pageSheet",
                                               readerMode=True))
        assert res == {"type": "cancel"}
        o = gate["opts"]
        assert o["toolbarColor"] == 0xFFFF0000 and o["controlsColor"] == 0xFFFFFFFF
        assert o["dismissButtonStyle"] == "close" and o["presentationStyle"] == "pageSheet" and o["readerMode"] is True
        assert o["secondaryToolbarColor"] is None and o["createTask"] is True

        async def two_at_once():
            WebBrowser._busy = True  # a browser is already up
            try:
                return await WebBrowser.open_browser_async("https://pyxpo.dev")
            finally:
                WebBrowser._busy = False
        assert run(two_at_once()) == {"type": "locked"}
        assert len([c for c in fb.calls if c[1] == "open"]) == 1


def test_ios_auth():
    with FakeBridge("ios") as fb:
        fb.on("WebBrowser", "auth", lambda url, redirect, opts: {"type": "success", "url": redirect + "?code=1"})
        res = run(WebBrowser.open_auth_session_async("https://a.example/auth", "app://cb",
                                                     prefer_ephemeral_session=True))
        assert res == {"type": "success", "url": "app://cb?code=1"}
        assert fb.calls[-1][2][2]["preferEphemeralSession"] is True
        fb.on("WebBrowser", "dismissAuth", lambda: None)
        WebBrowser.dismiss_auth_session()
        assert fb.calls[-1][:2] == ("WebBrowser", "dismissAuth")
        assert run(WebBrowser.warm_up_async()) == {}
        with pytest.raises(NotSupportedError):
            run(WebBrowser.get_custom_tabs_supporting_browsers_async())


def test_android_auth_redirect():
    with FakeBridge("android") as fb:
        def opener(url, opts):
            assert opts["createTask"] is False
            # The browser leaves, then the redirect deep link arrives.
            asyncio.get_running_loop().call_soon(_events.emit, "app_state", {"state": "background"})
            asyncio.get_running_loop().call_soon(_events.emit, "url", {"url": "other://x"})
            asyncio.get_running_loop().call_soon(_events.emit, "url", {"url": "app://cb?code=7"})
            return {"type": "opened"}
        fb.on("WebBrowser", "open", opener)

        before = {k: len(v) for k, v in _events._listeners.items()}
        assert run(WebBrowser.open_auth_session_async("https://a.example/auth", "app://cb")) == {
            "type": "success", "url": "app://cb?code=7"}
        assert {k: len(v) for k, v in _events._listeners.items() if v or k in before} == before
        _events.emit("app_state", {"state": "active"})


def test_android_auth_user_came_back():
    with FakeBridge("android") as fb:
        def opener(url, opts):
            loop = asyncio.get_running_loop()
            loop.call_soon(_events.emit, "app_state", {"state": "background"})
            loop.call_soon(_events.emit, "app_state", {"state": "active"})
            return {"type": "opened"}
        fb.on("WebBrowser", "open", opener)
        assert run(WebBrowser.open_auth_session_async("https://a.example/auth", "app://cb")) == {"type": "dismiss"}


def test_android_dismiss_auth_and_service():
    with FakeBridge("android") as fb:
        fb.on("WebBrowser", "open", lambda url, opts: {"type": "opened"})
        fb.on("WebBrowser", "dismiss", lambda: {"type": "dismiss"})

        async def go():
            task = asyncio.ensure_future(WebBrowser.open_auth_session_async("https://a.example/auth", "app://cb"))
            await asyncio.sleep(0.05)
            locked = await WebBrowser.open_auth_session_async("https://a.example/auth", "app://cb")
            WebBrowser.dismiss_auth_session()
            return locked, await task
        assert run(go()) == ({"type": "locked"}, {"type": "dismiss"})

        fb.on("WebBrowser", "warmUp", lambda pkg: {"servicePackage": pkg or "com.android.chrome"})
        fb.on("WebBrowser", "mayInitWithUrl", lambda url, pkg: {"servicePackage": "com.android.chrome"})
        fb.on("WebBrowser", "coolDown", lambda pkg: {})
        fb.on("WebBrowser", "browsers", lambda: {"browserPackages": ["com.android.chrome"], "servicePackages": [],
                                                 "defaultBrowserPackage": "", "preferredBrowserPackage": None})
        assert run(WebBrowser.warmUpAsync()) == {"servicePackage": "com.android.chrome"}
        assert run(WebBrowser.may_init_with_url_async("https://pyxpo.dev"))["servicePackage"] == "com.android.chrome"
        assert run(WebBrowser.cool_down_async("org.mozilla.firefox")) == {}
        b = run(WebBrowser.getCustomTabsSupportingBrowsersAsync())
        assert b["browserPackages"] == ["com.android.chrome"] and b["defaultBrowserPackage"] is None
        assert run(WebBrowser.open_browser_async("https://pyxpo.dev")) == {"type": "opened"}
