"""Shared ImageKit widgets."""
from pyxpo import ActivityIndicator, Image, KeyboardAvoidingView, Pressable, ScrollView, Text, View, component, useSafeAreaInsets
from pyxpo.router import router
from pyxpo.vector_icons import Feather

from app._theme import useTheme


def widget(fn):
    """@component whose positional args are props (a bare component call treats positionals as children)."""
    import inspect
    comp, names = component(fn), list(inspect.signature(fn).parameters)

    def make(*args, **kw):
        return comp(**dict(zip(names, args)), **kw)
    make.__name__ = fn.__name__
    return make


def shadow(t, o=0.12):
    return {"shadowColor": t["shadow"], "shadowOpacity": o, "shadowRadius": 14, "shadowOffset": {"width": 0, "height": 6}, "elevation": 4}


@component
def Screen(*children, title=None, back=True, scroll=True, footer=None):
    t, insets = useTheme(), useSafeAreaInsets()
    head = View(
        Pressable(Feather(name="arrow-left", size=22, color=t["text"]), onPress=router.back, hitSlop=12,
                  style={"width": 40, "height": 40, "borderRadius": 20, "backgroundColor": t["card"], "alignItems": "center", "justifyContent": "center", **shadow(t, 0.08)})
        if back else View(style={"width": 40}),
        Text(title or "", style={"fontSize": 20, "fontWeight": "700", "color": t["text"], "marginLeft": 12}),
        style={"flexDirection": "row", "alignItems": "center", "paddingHorizontal": 20, "paddingTop": insets["top"] + 8, "paddingBottom": 8},
    ) if title is not None else View(style={"height": insets["top"]})
    body = ScrollView(*children, contentContainerStyle={"padding": 20, "gap": 16, "paddingBottom": 32}, style={"flex": 1}) if scroll \
        else View(*children, style={"flex": 1, "padding": 20, "gap": 16})
    return KeyboardAvoidingView(head, body, footer and View(footer, style={"padding": 20, "paddingBottom": insets["bottom"] + 12, "backgroundColor": t["card"], "borderTopWidth": 1, "borderColor": t["line"]}),
                                behavior="padding", style={"flex": 1, "backgroundColor": t["bg"]})


@component
def Card(*children, style=None):
    t = useTheme()
    return View(*children, style=[{"backgroundColor": t["card"], "borderRadius": 20, "padding": 16, "gap": 12, **shadow(t, 0.06)}, style])


@widget
def Button(label, onPress, icon=None, kind="primary", busy=False, disabled=False):
    t = useTheme()
    primary = kind == "primary"
    fg = t["onAccent"] if primary else t["chipText"]
    st = {"height": 54, "borderRadius": 16, "flexDirection": "row", "alignItems": "center", "justifyContent": "center", "gap": 8,
          "opacity": 0.5 if disabled else 1}
    st.update({"linearGradient": {"angle": 90, "colors": [t["accent"], t["accent2"]]}} if primary else {"backgroundColor": t["chip"]})
    return Pressable(
        ActivityIndicator(color=fg) if busy else (Feather(name=icon, size=20, color=fg) if icon else None),
        None if busy else Text(label, style={"fontSize": 16, "fontWeight": "700", "color": fg}),
        onPress=None if (disabled or busy) else onPress, style=st)


@widget
def Chip(label, active, onPress):
    t = useTheme()
    return Pressable(
        Text(label, style={"fontSize": 14, "fontWeight": "600", "color": t["onAccent"] if active else t["chipText"]}),
        onPress=onPress,
        style={"paddingHorizontal": 16, "paddingVertical": 10, "borderRadius": 14, "backgroundColor": t["accent"] if active else t["chip"]})


@widget
def Thumb(uri, size=72, radius=14):
    t = useTheme()
    return Image(source=uri, resizeMode="cover", style={"width": size, "height": size, "borderRadius": radius, "overflow": "hidden", "flexShrink": 0, "flexGrow": 0, "backgroundColor": t["line"]})


@widget
def Row(label, value, strong=False):
    t = useTheme()
    return View(Text(label, style={"fontSize": 14, "color": t["sub"]}),
                Text(str(value), style={"fontSize": 14, "fontWeight": "700" if strong else "500", "color": t["text"]}),
                style={"flexDirection": "row", "justifyContent": "space-between"})
