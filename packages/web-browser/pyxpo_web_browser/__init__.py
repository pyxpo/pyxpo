"""In-app browser and OAuth sign-in sessions: the expo-web-browser API.

    import pyxpo_web_browser as WebBrowser

    result = await WebBrowser.open_browser_async("https://pyxpo.dev", toolbar_color="#202020")
    result["type"]            # iOS: "cancel" (user closed it) or "dismiss" (dismiss_browser); Android: "opened"

    result = await WebBrowser.open_auth_session_async(
        "https://auth.example.com/authorize?client_id=...&redirect_uri=myapp://callback", "myapp://callback")
    if result["type"] == "success":
        code = parse_qs(urlparse(result["url"]).query)["code"][0]

iOS uses SFSafariViewController and ASWebAuthenticationSession; Android uses Custom Tabs, with the sign-in
redirect coming back as a deep link to the app (the redirect URL must use the app's scheme).
"""
from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any, Dict, List, Optional

from pyxpo.module_api import NotSupportedError, call, platform, require_linked, require_supported

__version__ = "0.1.0a1"

Result = Dict[str, Any]


class WebBrowserResultType(str, Enum):
    CANCEL = "cancel"
    DISMISS = "dismiss"
    OPENED = "opened"
    LOCKED = "locked"


class WebBrowserPresentationStyle(str, Enum):
    """iOS modal presentation of the browser."""
    FULL_SCREEN = "fullScreen"
    PAGE_SHEET = "pageSheet"
    FORM_SHEET = "formSheet"
    CURRENT_CONTEXT = "currentContext"
    OVER_FULL_SCREEN = "overFullScreen"
    OVER_CURRENT_CONTEXT = "overCurrentContext"
    POPOVER = "popover"
    AUTOMATIC = "automatic"


_DISMISS_STYLES = ("done", "close", "cancel")
_busy = False


def _native() -> None:
    require_linked("WebBrowser", "web-browser", package="pyxpo-web-browser")


def _color(value: Any) -> Optional[int]:
    if value is None:
        return None
    from pyxpo.style import parse_color
    return parse_color(value)


def _check_url(url: str) -> str:
    if not isinstance(url, str) or not url:
        raise ValueError("url must be a non-empty string")
    scheme = url.split(":", 1)[0].lower() if ":" in url else ""
    if scheme not in ("http", "https"):
        raise ValueError("the browser opens http and https URLs only, got %r" % url)
    return url


def _options(toolbar_color: Any = None, secondary_toolbar_color: Any = None, controls_color: Any = None,
             enable_bar_collapsing: bool = False, show_title: bool = False,
             enable_default_share_menu_item: bool = False, show_in_recents: bool = False, create_task: bool = True,
             browser_package: Optional[str] = None, dismiss_button_style: str = "done", reader_mode: bool = False,
             presentation_style: Any = WebBrowserPresentationStyle.OVER_FULL_SCREEN) -> Dict[str, Any]:
    if dismiss_button_style not in _DISMISS_STYLES:
        raise ValueError("dismiss_button_style must be one of %s" % (_DISMISS_STYLES,))
    style = WebBrowserPresentationStyle(presentation_style).value
    return {
        "toolbarColor": _color(toolbar_color), "secondaryToolbarColor": _color(secondary_toolbar_color),
        "controlsColor": _color(controls_color), "enableBarCollapsing": bool(enable_bar_collapsing),
        "showTitle": bool(show_title), "enableDefaultShareMenuItem": bool(enable_default_share_menu_item),
        "showInRecents": bool(show_in_recents), "createTask": bool(create_task),
        "browserPackage": browser_package or "", "dismissButtonStyle": dismiss_button_style,
        "readerMode": bool(reader_mode), "presentationStyle": style,
    }


_CAMEL = {"toolbarColor": "toolbar_color", "secondaryToolbarColor": "secondary_toolbar_color",
          "controlsColor": "controls_color", "enableBarCollapsing": "enable_bar_collapsing", "showTitle": "show_title",
          "enableDefaultShareMenuItem": "enable_default_share_menu_item", "showInRecents": "show_in_recents",
          "createTask": "create_task", "browserPackage": "browser_package", "dismissButtonStyle": "dismiss_button_style",
          "readerMode": "reader_mode", "presentationStyle": "presentation_style",
          "preferEphemeralSession": "prefer_ephemeral_session"}


def _snake(opts: Dict[str, Any]) -> Dict[str, Any]:
    return {_CAMEL.get(k, k): v for k, v in opts.items()}


async def open_browser_async(url: str, **options: Any) -> Result:
    """Opens `url` in an in-app browser. Options (all optional): `toolbar_color`, `secondary_toolbar_color`
    (Android), `controls_color` (iOS), `enable_bar_collapsing`, `show_title` (Android),
    `enable_default_share_menu_item` (Android), `show_in_recents` (Android), `create_task` (Android),
    `browser_package` (Android), `dismiss_button_style` (iOS: "done", "close", "cancel"), `reader_mode` (iOS),
    `presentation_style` (iOS).

    iOS resolves when the browser closes: `{"type": "cancel"}` when the user closed it, `{"type": "dismiss"}`
    after `dismiss_browser()`, `{"type": "locked"}` when another browser is already open. Android resolves at
    once with `{"type": "opened"}`."""
    global _busy
    _check_url(url)
    opts = _options(**_snake(options))
    p = platform()
    if p == "desktop":
        import webbrowser
        await asyncio.to_thread(webbrowser.open, url)
        return {"type": "opened"}
    _native()
    if p == "ios":
        if _busy:
            return {"type": "locked"}
        _busy = True
        try:
            return dict(await call("WebBrowser", "open", url, opts, reply=True))
        finally:
            _busy = False
    return dict(await call("WebBrowser", "open", url, opts, reply=True))


async def dismiss_browser() -> Result:
    """Closes the browser opened by `open_browser_async`; its call resolves with `{"type": "dismiss"}`.
    On Android this brings the app back to the front."""
    if platform() == "desktop":
        return {"type": "dismiss"}
    _native()
    return dict(await call("WebBrowser", "dismiss", reply=True))


async def open_auth_session_async(url: str, redirect_url: Optional[str] = None, **options: Any) -> Result:
    """Opens a sign-in page and waits for it to redirect to `redirect_url` (normally `"<app scheme>://..."`).

    Returns `{"type": "success", "url": <the redirect URL with its query>}`, `{"type": "cancel"}` when the user
    closed the page, `{"type": "dismiss"}` after `dismiss_auth_session()` or (Android) when the user came back
    to the app without finishing, or `{"type": "locked"}` when a session is already open.

    `prefer_ephemeral_session=True` (iOS) shares no cookies with Safari and skips the "wants to use ... to sign
    in" prompt. Other options are those of `open_browser_async` (Android)."""
    global _busy
    _check_url(url)
    ephemeral = bool(options.pop("prefer_ephemeral_session", options.pop("preferEphemeralSession", False)))
    opts = _options(**_snake(options))
    p = platform()
    if p == "desktop":
        raise NotSupportedError("open_auth_session_async needs iOS or Android: desktop apps get no redirect")
    _native()
    if _busy:
        return {"type": "locked"}
    _busy = True
    try:
        if p == "ios":
            opts["preferEphemeralSession"] = ephemeral
            return dict(await call("WebBrowser", "auth", url, redirect_url or "", opts, reply=True))
        return await _android_auth(url, redirect_url or "", opts)
    finally:
        _busy = False


_auth_future: Optional["asyncio.Future[Result]"] = None


async def _android_auth(url: str, redirect_url: str, opts: Dict[str, Any]) -> Result:
    """Custom Tabs have no sign-in session: open the page, then wait for the redirect deep link, or for the
    user to come back to the app without it."""
    global _auth_future
    from pyxpo import AppState, Linking

    loop = asyncio.get_running_loop()
    fut: "asyncio.Future[Result]" = loop.create_future()
    _auth_future = fut
    left = {"away": False}

    def settle(result: Result) -> None:
        if not fut.done():
            fut.set_result(result)

    def on_url(event: Any) -> None:
        u = event.get("url") if isinstance(event, dict) else event
        if isinstance(u, str) and (not redirect_url or u.startswith(redirect_url)):
            settle({"type": "success", "url": u})

    def on_state(state: Any) -> None:
        if state != "active":
            left["away"] = True
        elif left["away"]:
            # The redirect's url event can come just after the app becomes active.
            loop.call_later(0.6, settle, {"type": "dismiss"})

    subs = [Linking.addEventListener("url", on_url), AppState.addEventListener("change", on_state)]
    try:
        opts["createTask"] = False  # the redirect then closes the tab: the app's activity is singleTask
        await call("WebBrowser", "open", url, opts, reply=True)
        return await fut
    finally:
        _auth_future = None
        for s in subs:
            s.remove()


def dismiss_auth_session() -> None:
    """Closes the open sign-in session; its call resolves with `{"type": "dismiss"}`."""
    p = platform()
    if p == "desktop":
        return
    _native()
    if p == "ios":
        call("WebBrowser", "dismissAuth", reply=False)
        return
    fut = _auth_future
    if fut is not None and not fut.done():
        fut.set_result({"type": "dismiss"})
    call("WebBrowser", "dismiss", reply=False)


def maybe_complete_auth_session(**_: Any) -> Result:
    """Web only in Expo; native apps get their redirect from `open_auth_session_async`."""
    return {"type": "failed", "message": "Not supported on this platform"}


# Android Custom Tabs service: preload the browser and pages. iOS and desktop return {}.
async def warm_up_async(browser_package: Optional[str] = None) -> Result:
    if platform() != "android":
        return {}
    _native()
    return dict(await call("WebBrowser", "warmUp", browser_package or "", reply=True))


async def may_init_with_url_async(url: str, browser_package: Optional[str] = None) -> Result:
    if platform() != "android":
        return {}
    _check_url(url)
    _native()
    return dict(await call("WebBrowser", "mayInitWithUrl", url, browser_package or "", reply=True))


async def cool_down_async(browser_package: Optional[str] = None) -> Result:
    if platform() != "android":
        return {}
    _native()
    return dict(await call("WebBrowser", "coolDown", browser_package or "", reply=True))


async def get_custom_tabs_supporting_browsers_async() -> Dict[str, Any]:
    """Android: `{"browserPackages", "defaultBrowserPackage", "servicePackages", "preferredBrowserPackage"}`."""
    require_supported("get_custom_tabs_supporting_browsers_async", ios=False)
    if platform() == "desktop":
        return {"browserPackages": [], "defaultBrowserPackage": None, "servicePackages": [],
                "preferredBrowserPackage": None}
    _native()
    out = dict(await call("WebBrowser", "browsers", reply=True))
    for k in ("defaultBrowserPackage", "preferredBrowserPackage"):
        out[k] = out.get(k) or None
    return out


openBrowserAsync = open_browser_async
dismissBrowser = dismiss_browser
openAuthSessionAsync = open_auth_session_async
dismissAuthSession = dismiss_auth_session
maybeCompleteAuthSession = maybe_complete_auth_session
warmUpAsync = warm_up_async
mayInitWithUrlAsync = may_init_with_url_async
coolDownAsync = cool_down_async
getCustomTabsSupportingBrowsersAsync = get_custom_tabs_supporting_browsers_async

__all__ = ["open_browser_async", "dismiss_browser", "open_auth_session_async", "dismiss_auth_session",
           "maybe_complete_auth_session", "warm_up_async", "may_init_with_url_async", "cool_down_async",
           "get_custom_tabs_supporting_browsers_async", "WebBrowserResultType", "WebBrowserPresentationStyle"]
