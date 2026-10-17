"""Shared ImageKit widgets."""
from pyxpo import ActivityIndicator, Container, Image, KeyboardAvoidingView, Pressable, ScrollView, StyleSheet, Text, View, component, useAppTheme
from pyxpo.router import router
from pyxpo.vector_icons import Feather

from app._theme import shadow


def widget(fn):
    """@component whose positional args are props (a bare component call treats positionals as children)."""
    import inspect
    comp, names = component(fn), list(inspect.signature(fn).parameters)

    def make(*args, **kw):
        return comp(**dict(zip(names, args)), **kw)
    make.__name__ = fn.__name__
    return make


@component
def Screen(*children, title=None, back=True, scroll=True, footer=None):
    theme = useAppTheme()  # for the icon color; styles follow the theme by themselves
    # Header, body and footer share one centered Container column, so wide screens get a readable page, not a stretched phone UI.
    head = View(Container(View(
        Pressable(Feather(name="arrow-left", size=22, color=theme.colors.text), onPress=router.back, hitSlop=12, style=styles.backButton)
        if back else View(style=styles.backSpacer),
        Text(title or "", style=styles.title),
        style=styles.headerRow), padding=20),
        style=styles.header,
    ) if title is not None else View(style=styles.topInset)
    page = Container(*children, padding=20, style=styles.page)
    body = ScrollView(page, contentContainerStyle=styles.scrollContent, style=styles.body) if scroll else View(page, style=styles.staticBody)
    foot = footer and View(Container(View(footer, style=styles.footerInner), padding=20),
                           style=styles.footer)
    return KeyboardAvoidingView(head, body, foot, behavior="padding", style=styles.screen)


@component
def Card(*children, style=None):
    return View(*children, style=[styles.card, style])


@widget
def Button(label, onPress, icon=None, kind="primary", busy=False, disabled=False):
    theme = useAppTheme()
    primary = kind == "primary"
    fg = theme.colors.onAccent if primary else theme.colors.chipText
    return Pressable(
        ActivityIndicator(color=fg) if busy else (Feather(name=icon, size=20, color=fg) if icon else None),
        None if busy else Text(label, style=[styles.buttonLabel, {"color": fg}]),
        onPress=None if (disabled or busy) else onPress,
        style=[styles.button, styles.buttonPrimary if primary else styles.buttonSecondary, disabled and styles.disabled])


@widget
def Chip(label, active, onPress):
    return Pressable(Text(label, style=[styles.chipLabel, active and styles.chipLabelActive]),
                     onPress=onPress, style=[styles.chip, active and styles.chipActive])


@widget
def Thumb(uri, size=72, radius=14):
    return Image(source=uri, resizeMode="cover", style=styles.thumb(size, radius))


@widget
def Row(label, value, strong=False):
    return View(Text(label, style=styles.infoLabel),
                Text(str(value), style=[styles.infoValue, strong and styles.infoValueStrong]),
                style=styles.infoRow)


styles = StyleSheet.create(lambda theme, rt: {
    # Screen
    "screen": {"flex": 1, "backgroundColor": theme.colors.bg},
    "header": {"paddingTop": rt.insets.top + 8, "paddingBottom": 8},
    "topInset": {"height": rt.insets.top},
    "headerRow": {"flexDirection": "row", "alignItems": "center"},
    "backButton": {"width": 40, "height": 40, "borderRadius": 20, "backgroundColor": theme.colors.card,
                   "alignItems": "center", "justifyContent": "center", **shadow(theme, 0.08)},
    "backSpacer": {"width": 40},
    "title": {"fontSize": {"base": 20, "lg": 26}, "fontWeight": "700", "color": theme.colors.text, "marginLeft": 12},
    "page": {"gap": 16},
    "body": {"flex": 1},
    "scrollContent": {"paddingTop": {"base": 20, "lg": 28}, "paddingBottom": 32},
    "staticBody": {"flex": 1, "paddingVertical": 20},
    "footer": {"paddingTop": 20, "paddingBottom": rt.insets.bottom + 12, "backgroundColor": theme.colors.card, "borderTopWidth": 1, "borderColor": theme.colors.line},
    # Footer action: full width on phones, a right-aligned 420 dp block from md up.
    "footerInner": {"width": "100%", "maxWidth": {"base": None, "md": 420}, "alignSelf": {"base": "stretch", "md": "flex-end"}},

    # Card
    "card": {"backgroundColor": theme.colors.card, "borderRadius": 20, "padding": 16, "gap": 12, **shadow(theme, 0.06)},

    # Button
    "button": {"height": 54, "borderRadius": 16, "flexDirection": "row", "alignItems": "center", "justifyContent": "center", "gap": 8},
    "buttonPrimary": {"linearGradient": {"angle": 90, "colors": [theme.colors.accent, theme.colors.accent2]}},
    "buttonSecondary": {"backgroundColor": theme.colors.chip},
    "buttonLabel": {"fontSize": 16, "fontWeight": "700"},
    "disabled": {"opacity": 0.5},

    # Chip
    "chip": {"paddingHorizontal": 16, "paddingVertical": 10, "borderRadius": 14, "backgroundColor": theme.colors.chip},
    "chipActive": {"backgroundColor": theme.colors.accent},
    "chipLabel": {"fontSize": 14, "fontWeight": "600", "color": theme.colors.chipText},
    "chipLabelActive": {"color": theme.colors.onAccent},

    # Thumb
    "thumb": lambda size, radius: {"width": size, "height": size, "borderRadius": radius, "overflow": "hidden",
                                   "flexShrink": 0, "flexGrow": 0, "backgroundColor": theme.colors.line},

    # Row (label / value line)
    "infoRow": {"flexDirection": "row", "justifyContent": "space-between"},
    "infoLabel": {"fontSize": 14, "color": theme.colors.sub},
    "infoValue": {"fontSize": 14, "fontWeight": "500", "color": theme.colors.text},
    "infoValueStrong": {"fontWeight": "700"},
})
