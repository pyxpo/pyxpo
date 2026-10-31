"""`RouterRoot`: builds the Store and Runtime for a route tree and renders the root navigator."""
from __future__ import annotations

from typing import Any, Optional

from ..apis import _bridge, _events
from ..apis.linking import Linking
from ..apis.back_handler import BackHandler
from ..component import ErrorBoundary, component
from ..components.button import Button
from ..components.status_bar import StatusBar
from ..components.text import Text
from ..components.view import View
from ..hooks import use_color_scheme, use_effect, use_ref, use_state
from .discovery import Navigator, RouteTree, discover, load_module
from .matching import Href
from .router import router
from .runtime import Runtime, RuntimeContext
from .screen import NavigatorHost
from .store import Store


def _initial_names(root_dir: str):
    def names(nav: Navigator) -> Optional[str]:
        if nav.layout_module is None:
            return None
        mod = load_module(nav.layout_module, nav.layout_file, root_dir)
        return (getattr(mod, "unstable_settings", None) or {}).get("initialRouteName")
    return names


def _crash(error: Any, reset: Any):
    return View(Text("Something went wrong", style={"fontSize": 18, "fontWeight": "600", "marginBottom": 8}),
                Text(str(error), style={"color": "#8E8E93", "marginBottom": 16, "textAlign": "center"}),
                Button(title="Try again", onPress=reset),
                style={"flex": 1, "alignItems": "center", "justifyContent": "center", "padding": 24})


def href_from_url(url: str) -> Optional[str]:
    """`myapp://about?x=1`, `myapp:///about` and `https://host/about` -> `/about?x=1`; None if not a URL."""
    if "://" not in url:
        return None
    scheme, rest = url.split("://", 1)
    if scheme in ("http", "https"):
        rest = rest.partition("/")[2]
    return "/" + rest.lstrip("/")


def _on_hot_refresh(fn):
    """Re-discover routes before every hot re-render, so added/removed route files take effect."""
    hooks = _bridge.get_app().hot_hooks
    hooks.append(fn)
    return lambda: fn in hooks and hooks.remove(fn)


@component
def RouterRoot(tree: Optional[RouteTree] = None, root_dir: str = "", initial_href: Href = "/"):
    _, tick = use_state(0)
    holder = use_ref(None)
    if holder.current is None:
        first = _bridge.get_app().env.get().get("initial_url")
        if first:
            Linking.initial_url = first
        store = Store(tree, href_from_url(first or "") or initial_href, _initial_names(root_dir))
        rt = Runtime(store, root_dir)
        bump = lambda: tick(lambda v: v + 1)  # noqa: E731
        store.subscribe(bump)
        rt.on_change = bump
        holder.current = rt
    rt = holder.current
    router._bind(rt.store)
    use_effect(lambda: BackHandler.addEventListener("hardwareBackPress", rt.store.back).remove, [])

    def on_url(payload: Any) -> None:
        url = str((payload or {}).get("url", ""))
        href = href_from_url(url)
        if href is not None and not Linking.is_claimed(url):
            rt.store.navigate(href)

    use_effect(lambda: _events.on("url", on_url), [])
    use_effect(lambda: _on_hot_refresh(lambda: rt.store.set_tree(discover(root_dir))), [])
    synced = use_ref(None)

    def sync_history() -> None:
        """Web: mirror the focused route into the address bar, browser history and document title."""
        if _bridge.get_app().env.get().get("os") != "web":
            return
        chain = rt.store.focused_chain()
        opts = rt.resolved.get(chain[-1][1]["key"]) or {} if chain else {}
        title = opts.get("title") if isinstance(opts.get("title"), str) else None
        cur = (rt.store.href, title)
        if cur != synced.current:
            synced.current = cur
            _bridge.call("History", "sync", *cur)

    use_effect(sync_history)  # every commit: navigators resolve screen titles while rendering below this root
    scheme = use_color_scheme()
    use_effect(lambda: StatusBar.set_bar_style("light-content" if scheme == "dark" else "dark-content"), [scheme])
    nav = rt.store.tree.root
    return ErrorBoundary(RuntimeContext.Provider(NavigatorHost(nav=nav, node_key=rt.store.state["key"]), value=rt),
                         fallback=_crash)
