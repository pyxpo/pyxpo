# pyxpo-web-browser

An in-app browser and OAuth sign-in sessions for [pyxpo](https://github.com/pyxpo/pyxpo) apps written in Python. The API follows
[expo-web-browser](https://docs.expo.dev/versions/latest/sdk/webbrowser/). iOS uses `SFSafariViewController` and
`ASWebAuthenticationSession`. Android uses Chrome Custom Tabs (`androidx.browser`). The user keeps their cookies, saved
passwords and autofill, and your app never sees them.

<p align="center">
  <img src="https://raw.githubusercontent.com/pyxpo/pyxpo-web-browser/main/docs/images/hero.png" width="820" alt="github.com open in the in-app browser, a Custom Tab on Android and Safari View Controller on iOS">
</p>

```python
import pyxpo_web_browser as WebBrowser

result = await WebBrowser.open_browser_async("https://pyxpo.dev", toolbar_color="#202020")
```

## Features

- **In-app browser** for any `http` or `https` page, with a colored toolbar.
- **OAuth sign-in:** `open_auth_session_async` waits for the redirect and returns the final URL.
- **Presentation options:** toolbar colors, share item, reader mode, bar collapsing, modal style.
- **Android Custom Tabs warm-up** (`warm_up_async`, `may_init_with_url_async`) for faster first paint.
- **Works on the desktop** by opening the system browser, so you can develop without a phone.
- **camelCase too:** `openBrowserAsync`, `toolbarColor=...`.

## Contents

| If you are... | Start here |
| --- | --- |
| Opening a link | [Quick start](#quick-start) |
| Styling the browser | [Options](#options) |
| Signing users in | [Sign-in](#sign-in) |
| Speeding up the first load | [Warm-up](#warm-up-android) |
| Exact names | [API reference](#api-reference) · [Errors](#errors) |
| A real use | [Recipe: sign in with an OAuth provider](#recipe-sign-in-with-an-oauth-provider) |
| Stuck | [Testing](#testing) · [Troubleshooting](#troubleshooting) · [FAQ](#faq) |

## Platform support

| Target | What works |
| --- | --- |
| Android, API 24+ | Custom Tabs. `open_browser_async` returns `{"type": "opened"}` at once. Sign-in comes back as a deep link. |
| iOS 15+ | `SFSafariViewController` and `ASWebAuthenticationSession`. The call resolves when the browser closes. |
| Desktop window and tests | `open_browser_async` opens the system browser. `open_auth_session_async` raises `NotSupportedError`. |
| Web page | Same as desktop. |

Requires Python 3.9+ and `pyxpo>=0.1.0a2`.

## Install

```sh
pip install pyxpo-web-browser
```

```toml
[tool.pyxpo]
scheme = "myapp"          # needed for sign-in redirects such as myapp://callback
modules = ["web-browser"]
```

Rebuild the app. There are no permissions and no Info.plist texts. The `scheme` is only needed if you use `open_auth_session_async`.

## Quick start

```python
from pyxpo import Button, Text, View, component, use_async, use_state
import pyxpo_web_browser as WebBrowser


@component
def Links():
    taps, set_taps = use_state(0)
    result, set_result = use_state(None)

    async def run():
        if taps > 0:
            set_result(await WebBrowser.open_browser_async(
                "https://github.com/pyxpo/pyxpo", toolbar_color="#1a73e8", controls_color="#ffffff"))

    use_async(run, [taps])

    return View(
        Button("Open pyxpo on GitHub", lambda: set_taps(taps + 1)),
        Text("result: %s" % (result,)),
    )
```

> **Tip:** on iOS the awaited result arrives when the user closes the browser: `{"type": "cancel"}`. On Android it arrives
> immediately with `{"type": "opened"}`. Never use `lambda: WebBrowser.open_browser_async(...)` as a handler: the coroutine would not be awaited.

<p align="center">
  <img src="https://raw.githubusercontent.com/pyxpo/pyxpo-web-browser/main/docs/images/opened.png" width="720" alt="The in-app browser open on github.com, on Android and iOS">
</p>

## Result types

| `type` | Meaning |
| --- | --- |
| `"opened"` | Android: the tab was opened. Desktop: the system browser was started. |
| `"cancel"` | iOS: the user closed the browser. Sign-in: the user closed the page. |
| `"dismiss"` | Your code called `dismiss_browser()` or `dismiss_auth_session()`. On Android sign-in it also means the user came back without finishing. |
| `"locked"` | Another browser or session is already open. |
| `"success"` | Sign-in only. `result["url"]` is the redirect URL including its query. |

`WebBrowserResultType` has these values as an enum.

## Options

Pass them as keyword arguments. camelCase names work too.

| Option | Platform | Notes |
| --- | --- | --- |
| `toolbar_color` | both | Any pyxpo color (`"#202020"`, `"orange"`). |
| `secondary_toolbar_color` | Android | |
| `controls_color` | iOS | Tint of the buttons. |
| `enable_bar_collapsing` | both | Hide the bar while scrolling. |
| `show_title` | Android | Show the page title. |
| `enable_default_share_menu_item` | Android | Add a Share item to the menu. |
| `show_in_recents` | Android | Keep the tab in the recent apps list (default off). |
| `create_task` | Android | Open the tab in its own task (default on). |
| `browser_package` | Android | Use this browser instead of the preferred one. |
| `dismiss_button_style` | iOS | `"done"`, `"close"` or `"cancel"`. Anything else raises `ValueError`. |
| `reader_mode` | iOS | Enter Reader when available. |
| `presentation_style` | iOS | A `WebBrowserPresentationStyle`: `FULL_SCREEN`, `PAGE_SHEET`, `FORM_SHEET`, `CURRENT_CONTEXT`, `OVER_FULL_SCREEN` (default), `OVER_CURRENT_CONTEXT`, `POPOVER`, `AUTOMATIC`. |
| `prefer_ephemeral_session` | iOS, sign-in | Share no cookies with Safari. This also skips the "wants to use ... to sign in" prompt. |

## Sign-in

```python
from urllib.parse import parse_qs, urlparse

result = await WebBrowser.open_auth_session_async(
    "https://auth.example.com/authorize?client_id=abc&redirect_uri=myapp%3A%2F%2Fcallback",
    "myapp://callback",
    prefer_ephemeral_session=True,
)
if result["type"] == "success":
    code = parse_qs(urlparse(result["url"]).query)["code"][0]
```

`redirect_url` must start with the app's `scheme`. On iOS the system watches for the redirect. On Android, Custom Tabs have no
sign-in session, so the package opens the page and waits for the redirect to arrive as a deep link. The tab opens in the app's
task and the redirect closes it. If the user returns to the app without the redirect, the call returns `{"type": "dismiss"}`.

Close an open page from code with `await WebBrowser.dismiss_browser()` or `WebBrowser.dismiss_auth_session()`.

> **Tip:** on Android 15 and later, a tab on top puts your app in the background. The system then blocks it from starting activities
> and freezes it after a few seconds. So `dismiss_browser()` called while a tab shows may not close it: the call returns and the app
> resumes when the user leaves the tab. Sign-in redirects are not affected, because the system delivers the deep link.

## Warm-up (Android)

```python
await WebBrowser.warm_up_async()                               # start the browser's service early
await WebBrowser.may_init_with_url_async("https://pyxpo.dev")  # preload a page the user will probably open
...
await WebBrowser.cool_down_async()
info = await WebBrowser.get_custom_tabs_supporting_browsers_async()
info["browserPackages"], info["defaultBrowserPackage"]
```

On iOS and desktop the warm-up functions return `{}`. `get_custom_tabs_supporting_browsers_async` raises `NotSupportedError` on iOS.

## Errors

| Error | When | What to do |
| --- | --- | --- |
| `ValueError` | The URL is empty, or its scheme is not `http` or `https`. A bad `dismiss_button_style`. | Pass a full `https://` URL. |
| `NotSupportedError` | `open_auth_session_async` on the desktop. `get_custom_tabs_supporting_browsers_async` on iOS. | Use a phone build, or branch on `platform()`. |
| `ModuleNotLinkedError` | The phone build lacks the module. | Add `"web-browser"` to `modules` and rebuild. |
| `{"type": "locked"}` result | A browser or sign-in is already open. | Wait for it to close. |

## Config

`scheme` in `[tool.pyxpo]` is the deep-link scheme for sign-in redirects. The package adds an Android `queries` entry so the app can find browsers and Custom Tabs services. Nothing else is needed.

## Web and desktop

`open_browser_async` calls Python's `webbrowser.open`, so the system browser opens. `dismiss_browser()` returns `{"type": "dismiss"}`
without closing anything. `maybe_complete_auth_session()` returns `{"type": "failed", "message": ...}`, because only Expo's web target uses it.

## Recipe: sign in with an OAuth provider

```python
from urllib.parse import parse_qs, urlencode, urlparse

from pyxpo import Button, Text, View, component, use_async, use_state
import pyxpo_web_browser as WebBrowser

AUTH = "https://auth.example.com/authorize"
REDIRECT = "myapp://callback"


@component
def SignIn():
    taps, set_taps = use_state(0)
    status, set_status = use_state("Signed out")

    async def run():
        if taps == 0:
            return
        url = AUTH + "?" + urlencode({"client_id": "abc", "redirect_uri": REDIRECT,
                                       "response_type": "code", "scope": "openid"})
        res = await WebBrowser.open_auth_session_async(url, REDIRECT, prefer_ephemeral_session=True)
        if res["type"] == "success":
            code = parse_qs(urlparse(res["url"]).query).get("code", [""])[0]
            set_status("Got a code (%d chars). Exchange it on your server." % len(code))
        elif res["type"] == "cancel":
            set_status("Cancelled")
        else:
            set_status("Result: %s" % res["type"])

    use_async(run, [taps])
    return View(Text(status), Button("Sign in", lambda: set_taps(taps + 1)))
```

## Production checklist

- [ ] `scheme` is set and unique to your app, and matches the redirect URL registered with the provider.
- [ ] You handle all of `success`, `cancel`, `dismiss` and `locked`.
- [ ] You use the PKCE flow or exchange the code on your server. Never ship a client secret in the app.
- [ ] You check the `state` value in the returned URL.
- [ ] Only `http` and `https` URLs from trusted sources are opened.
- [ ] Sign-in is tested on a real Android device and on iOS.

## Testing

Fake the module's native call and the platform to test your result handling:

```python
import asyncio

import pytest

import pyxpo_web_browser as wb


def test_rejects_non_http_urls():
    with pytest.raises(ValueError):
        asyncio.run(wb.open_browser_async("file:///etc/passwd"))


def test_desktop_opens_system_browser(monkeypatch):
    import webbrowser

    seen = []
    monkeypatch.setattr(webbrowser, "open", lambda url: seen.append(url) or True)
    res = asyncio.run(wb.open_browser_async("https://pyxpo.dev"))
    assert res == {"type": "opened"}
    assert seen == ["https://pyxpo.dev"]


def test_auth_needs_a_phone():
    from pyxpo.module_api import NotSupportedError

    with pytest.raises(NotSupportedError):
        asyncio.run(wb.open_auth_session_async("https://a.example/auth", "myapp://cb"))


def test_ios_result(monkeypatch):
    monkeypatch.setattr(wb, "platform", lambda: "ios")
    monkeypatch.setattr(wb, "require_linked", lambda *a, **k: None)

    async def fake_call(*args, **kwargs):
        return {"type": "cancel"}

    monkeypatch.setattr(wb, "call", fake_call)
    assert asyncio.run(wb.open_browser_async("https://pyxpo.dev")) == {"type": "cancel"}
```

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `ValueError` about the URL | Only `http` and `https` are allowed. |
| Sign-in never returns on Android | The redirect does not start with the app `scheme`, or the provider rejects it. Check both. |
| `"locked"` | A page is already open. |
| `dismiss_browser()` does nothing on Android 15+ | The system blocks it while a tab is on top. See the tip under [Sign-in](#sign-in). |
| iOS asks "wants to use ... to sign in" | Pass `prefer_ephemeral_session=True`. |
| Nothing opens on the desktop | The system browser may be missing. Check `webbrowser.open`. |
| `NotSupportedError` | You called a phone-only function on the desktop. |

## FAQ

**Is this a WebView?** No. It is the system's browser UI, so you get the user's cookies and autofill and cannot read the page.

**Can I read the page content?** No, by design.

**Which browser does Android use?** The preferred Custom Tabs browser. Set `browser_package` to choose.

**Can I pass `file://` or `tel:` links?** No: `http` and `https` only. Use `pyxpo.Linking` for other schemes.

## API reference

| Function | Returns |
| --- | --- |
| `open_browser_async(url, **options)` | A result dict. |
| `dismiss_browser()` | `{"type": "dismiss"}` (async). |
| `open_auth_session_async(url, redirect_url=None, **options)` | A result dict. |
| `dismiss_auth_session()` | `None`. |
| `maybe_complete_auth_session()` | `{"type": "failed"}`: web only in Expo. |
| `warm_up_async(browser_package=None)` | Android: dict. Elsewhere `{}`. |
| `may_init_with_url_async(url, browser_package=None)` | Android: dict. Elsewhere `{}`. |
| `cool_down_async(browser_package=None)` | Android: dict. Elsewhere `{}`. |
| `get_custom_tabs_supporting_browsers_async()` | Android: `browserPackages`, `servicePackages`, `defaultBrowserPackage`, `preferredBrowserPackage`. |
| `WebBrowserResultType`, `WebBrowserPresentationStyle` | Enums. |

## License

MIT
