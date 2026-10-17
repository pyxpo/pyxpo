"""Themes for `StyleSheet`, modeled on react-native-unistyles 3.

Register the themes once, then give `StyleSheet.create` a function instead of a dict:

    StyleSheet.configure(themes={"light": light, "dark": dark})   # adaptive: follows the system color scheme

    styles = StyleSheet.create(lambda theme, rt: {
        "screen": {"flex": 1, "backgroundColor": theme.colors.bg, "paddingTop": rt.insets.top},
        "title": {"fontSize": {"base": 20, "lg": 26}, "color": theme.colors.text},
        "thumb": lambda size: {"width": size, "height": size},     # dynamic style: styles.thumb(56)
    })

    View(Text("Hi", style=styles.title), style=styles.screen)

Components need no hook. The reconciler resolves themed styles when it renders a view and re-styles those views
when the theme, safe-area insets or breakpoint change, with no re-render (like breakpoint maps, see
`pyxpo.responsive`). For the theme in component code (icon colors and the like) use `useAppTheme()`.

`rt` (the mini runtime) holds `insets`, `breakpoint`, `color_scheme` / `colorScheme`, `theme_name` / `themeName`
and `font_scale` / `fontScale`. Window size is left out on purpose: use breakpoint maps for that.
"""
from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, List, Optional, Tuple

_themes: Dict[str, "AttrDict"] = {}
_adaptive = True
_chosen: Optional[str] = None
_listeners: List[Callable[[], None]] = []


class AttrDict(dict):
    """dict that also reads keys as attributes: `theme.colors.text` or `theme["colors"]["text"]`."""

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        try:
            return self[name]
        except KeyError:
            raise AttributeError("no key %r (have %s)" % (name, ", ".join(map(str, self)))) from None

    def __dir__(self) -> List[str]:
        return list(super().__dir__()) + [k for k in self if isinstance(k, str)]


def _attrs(v: Any) -> Any:
    if isinstance(v, dict):
        return AttrDict((k, _attrs(x)) for k, x in v.items())
    return v


def configure(themes: Optional[Dict[str, Dict[str, Any]]] = None, *, breakpoints: Optional[Dict[str, int]] = None,
              adaptive_themes: Optional[bool] = None, initial_theme: Optional[str] = None) -> None:
    """Registers themes (and optionally a breakpoint table). `adaptive_themes` (default on) picks the "light" or
    "dark" theme from the system color scheme; with it off the app shows `initial_theme` (default: the first
    theme) until `set_theme`. Call it once at import time, before the app renders; calling it again replaces it."""
    global _themes, _adaptive, _chosen
    if themes is not None:
        if not isinstance(themes, dict) or not themes:
            raise ValueError("StyleSheet.configure: themes must be a non-empty dict of {name: theme}")
        _themes = {str(k): _attrs(v) for k, v in themes.items()}
    if breakpoints is not None:
        from . import responsive
        responsive.set_breakpoints(breakpoints)
    if adaptive_themes is not None:
        _adaptive = bool(adaptive_themes)
    if initial_theme is not None:
        _check(initial_theme)
    _chosen = initial_theme
    _notify()


def _check(name: str) -> None:
    if name not in _themes:
        raise ValueError("unknown theme %r (have %s)" % (name, ", ".join(_themes) or "none: call StyleSheet.configure"))


def set_theme(name: str) -> None:
    """Shows theme `name` and turns adaptive themes off (`set_adaptive_themes(True)` follows the system again)."""
    global _adaptive, _chosen
    _check(name)
    _adaptive, _chosen = False, name
    _notify()


def set_adaptive_themes(on: bool) -> None:
    global _adaptive
    _adaptive = bool(on)
    _notify()


def theme_name(color_scheme: Optional[str] = None) -> Optional[str]:
    """Name of the theme on screen for a system `color_scheme` (None when no theme is configured)."""
    if not _themes:
        return None
    if _adaptive and color_scheme in _themes:
        return color_scheme
    if _chosen is not None:
        return _chosen
    return next(iter(_themes))


def get(name: Optional[str]) -> AttrDict:
    return _themes[name] if name in _themes else AttrDict()


def subscribe(fn: Callable[[], None]) -> Callable[[], None]:
    _listeners.append(fn)

    def off() -> None:
        if fn in _listeners:
            _listeners.remove(fn)
    return off


_version = 0


def version() -> int:
    """Bumped by every theme change (configure, set_theme, set_adaptive_themes)."""
    return _version


def _notify() -> None:
    global _version
    _version += 1
    for fn in list(_listeners):
        fn()


class Runtime(AttrDict):
    """`rt` in `StyleSheet.create(lambda theme, rt: ...)`."""


class Context:
    """Everything a themed style can depend on, read from one env snapshot. `key` is the theme-only cache key,
    `rt_key` adds what `rt` exposes."""
    __slots__ = ("theme", "rt", "key", "rt_key")

    def __init__(self, env: Dict[str, Any], breakpoint: str) -> None:
        scheme = env.get("color_scheme") or "light"
        name = theme_name(scheme)
        ins = env.get("insets") or {}
        insets = AttrDict((e, float(ins.get(e) or 0)) for e in ("top", "right", "bottom", "left"))
        fs = env.get("font_scale") or 1.0
        self.theme = get(name)
        self.rt = Runtime(insets=insets, breakpoint=breakpoint, color_scheme=scheme, colorScheme=scheme,
                          theme_name=name, themeName=name, font_scale=fs, fontScale=fs)
        self.key = (name, id(_themes))
        self.rt_key = (self.key, breakpoint, scheme, tuple(insets.values()), fs)


def current_context() -> Context:
    """Context of the running app (outside the reconciler, e.g. a style read in component code)."""
    from . import responsive
    from .apis import _env
    data = _env.current._data
    return Context(data, responsive.breakpoint_for(data["window"]["width"] or 0))


class ThemedSheet:
    """Result of `StyleSheet.create(fn)`. `styles.name` is a `ThemedStyle`; a dynamic entry (a function in the
    sheet) comes back as a function: `styles.thumb(56)`."""

    def __init__(self, factory: Callable[..., Dict[str, Any]]) -> None:
        try:
            n = len(inspect.signature(factory).parameters)
        except (TypeError, ValueError):
            n = 1
        self._factory = factory
        self._uses_rt = n >= 2
        self._sheets: Dict[Any, Dict[str, Any]] = {}

    def build(self, ctx: Context) -> Dict[str, Any]:
        """The sheet for one context: built and validated once per theme (and per `rt` when the factory takes it)."""
        key = ctx.rt_key if self._uses_rt else ctx.key
        sheet = self._sheets.get(key)
        if sheet is None:
            from .style import StyleSheet
            args = (ctx.theme, ctx.rt) if self._uses_rt else (ctx.theme,)
            sheet = StyleSheet.create(self._factory(*args))
            if len(self._sheets) > 32:
                self._sheets.clear()
            self._sheets[key] = sheet
        return sheet

    def resolve(self, name: str, args: Tuple[Any, ...], kwargs: Dict[str, Any], ctx: Context) -> Dict[str, Any]:
        entry = self.build(ctx)[name]
        if callable(entry):
            return dict(entry(*args, **kwargs))
        if args or kwargs:
            raise TypeError("style %r is not a function, use styles.%s without ()" % (name, name))
        return entry

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        ctx = current_context()
        try:
            entry = self.build(ctx)[name]
        except KeyError:
            raise AttributeError("no style named %r" % name) from None
        if callable(entry):
            def dynamic(*args: Any, **kwargs: Any) -> ThemedStyle:
                return ThemedStyle(self, name, args, kwargs, ctx)
            dynamic.__name__ = name
            return dynamic
        return ThemedStyle(self, name, (), {}, ctx)

    __getitem__ = __getattr__

    def __dir__(self) -> List[str]:
        return list(self.build(current_context()))


class ThemedStyle(dict):
    """One themed style. It holds the values for the context it was read in (so `{**styles.card}` and
    `StyleSheet.flatten` work), and the reconciler re-reads it for the context it renders in."""
    __slots__ = ("sheet", "name", "args", "kwargs")

    def __init__(self, sheet: ThemedSheet, name: str, args: Tuple[Any, ...], kwargs: Dict[str, Any],
                 ctx: Context) -> None:
        super().__init__(sheet.resolve(name, args, kwargs, ctx))
        self.sheet, self.name, self.args, self.kwargs = sheet, name, args, kwargs


def resolve_style(style: Any, ctx_fn: Callable[[], Context]) -> Tuple[Any, bool]:
    """(style with every `ThemedStyle` re-read for the context, whether it held any). A style without themed parts
    comes back as the same object. `ctx_fn` is only called when a themed style is found."""
    if style.__class__ is ThemedStyle:
        return style.sheet.resolve(style.name, style.args, style.kwargs, ctx_fn()), True
    if isinstance(style, (list, tuple)):
        used = False
        parts = []
        for s in style:
            s2, u = resolve_style(s, ctx_fn)
            used = used or u
            parts.append(s2)
        return (parts if used else style), used
    return style, False
