# pyxpo-web-browser

An in-app browser and OAuth sign-in sessions for [pyxpo](https://github.com/pyxpo/pyxpo) apps. The API follows
[expo-web-browser](https://docs.expo.dev/versions/latest/sdk/webbrowser/). iOS uses `SFSafariViewController` and
`ASWebAuthenticationSession`; Android uses Custom Tabs (`androidx.browser`).

```sh
pip install pyxpo-web-browser
```

```toml
[tool.pyxpo]
scheme = "myapp"
modules = ["web-browser"]
```

```python
import pyxpo_web_browser as WebBrowser

result = await WebBrowser.open_browser_async("https://pyxpo.dev", toolbar_color="#202020")

result = await WebBrowser.open_auth_session_async(
    "https://auth.example.com/authorize?client_id=abc&redirect_uri=myapp%3A%2F%2Fcallback", "myapp://callback")
if result["type"] == "success":
    query = parse_qs(urlparse(result["url"]).query)
```

## Functions

| Function | Notes |
| --- | --- |
| `open_browser_async(url, **options)` | Opens an `http` or `https` URL. iOS resolves when the browser closes: `{"type": "cancel"}` (the user closed it) or `{"type": "dismiss"}` (`dismiss_browser()`). Android resolves at once with `{"type": "opened"}`. `{"type": "locked"}` when a browser is already open (iOS). |
| `dismiss_browser()` | Closes the browser. On Android it brings the app back to the front. |
| `open_auth_session_async(url, redirect_url, **options)` | Opens a sign-in page and waits for a redirect to `redirect_url`. Returns `{"type": "success", "url"}`, `{"type": "cancel"}`, `{"type": "dismiss"}` or `{"type": "locked"}`. |
| `dismiss_auth_session()` | Closes the sign-in page; its call returns `{"type": "dismiss"}`. |
| `warm_up_async(browser_package=None)` | Android: starts the browser's Custom Tabs service early. Returns `{"servicePackage"}`. |
| `may_init_with_url_async(url, browser_package=None)` | Android: lets the browser preload `url`. |
| `cool_down_async(browser_package=None)` | Android: releases the service. |
| `get_custom_tabs_supporting_browsers_async()` | Android: `browserPackages`, `servicePackages`, `defaultBrowserPackage`, `preferredBrowserPackage`. |
| `maybe_complete_auth_session()` | Web only in Expo; returns `{"type": "failed"}` here. |

camelCase names work too (`openBrowserAsync`, `toolbarColor=...`).

## Options

| Option | Platform | Notes |
| --- | --- | --- |
| `toolbar_color` | both | Any pyxpo color (`"#202020"`, `"orange"`). |
| `secondary_toolbar_color` | Android | |
| `controls_color` | iOS | Tint of the buttons. |
| `enable_bar_collapsing` | both | Hide the bar while scrolling. |
| `show_title` | Android | Show the page title. |
| `enable_default_share_menu_item` | Android | |
| `show_in_recents` | Android | Keep the tab in the recent apps list (default off). |
| `create_task` | Android | Open the tab in its own task (default on). |
| `browser_package` | Android | Use this browser instead of the preferred one. |
| `dismiss_button_style` | iOS | `"done"`, `"close"` or `"cancel"`. |
| `reader_mode` | iOS | Enter Reader when available. |
| `presentation_style` | iOS | A `WebBrowserPresentationStyle`; default `overFullScreen`. |
| `prefer_ephemeral_session` | iOS, sign-in | Share no cookies with Safari. This also skips the "wants to use ... to sign in" prompt. |

## Sign-in on Android

Custom Tabs have no sign-in session. The package opens the page and waits for the redirect to come back as a deep
link, so `redirect_url` must use the app's `scheme`. The tab opens in the app's task, and the redirect closes it.
When the user returns to the app without the redirect, the call returns `{"type": "dismiss"}`.

## Android 15 and later

While a tab is on top, the app is in the background. Android 15+ blocks activity starts from background apps and
freezes their processes a few seconds later. So `dismiss_browser()` and `dismiss_auth_session()` called while
a tab is showing may not close it: the calls still return, and the app resumes when the user leaves the tab.
Sign-in redirects are not affected, because the system delivers the deep link.

## Platforms

iOS and Android. On desktop, `open_browser_async` opens the system browser and `open_auth_session_async` raises
`NotSupportedError`.
