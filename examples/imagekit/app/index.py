from pyxpo import Col, Container, Grid, Pressable, Row as GridRow, ScrollView, Text, View, VStack, StyleSheet, component, useEffect
from pyxpo.router import router
from pyxpo.apis import _bridge
from pyxpo.vector_icons import Feather

from app import _boot
from app._store import pick, useStore
from app._theme import TOOLS, fmt_bytes, shadow
from app._ui import Thumb


@component
def Home():
    st = useStore()
    useEffect(_boot.start, [])
    imgs = st["images"]

    def choose():
        _bridge.spawn(pick(True))

    def open_tool(tool):
        def go():
            if not imgs and tool["id"] != "info":
                async def flow():
                    if await pick(True):
                        router.push("/tool/" + tool["id"])
                _bridge.spawn(flow())
            else:
                router.push("/tool/" + tool["id"])
        return go

    hero = Pressable(
        View(Feather(name="image", size=30, color="#fff"), style=styles.heroIcon),
        View(Text("Choose photos" if not imgs else "%d photo%s selected" % (len(imgs), "" if len(imgs) == 1 else "s"), style=styles.heroTitle),
             Text("From your library · stays on this device" if not imgs else "Tap to change · %s total" % fmt_bytes(sum(i.get("fileSize") or 0 for i in imgs)), style=styles.heroSub),
             style=styles.heroText),
        Feather(name="chevron-right", size=22, color="#fff"),
        onPress=choose, style=styles.hero)

    strip = ScrollView(*[Thumb(i["uri"], 64, 14) for i in imgs], horizontal=True, showsHorizontalScrollIndicator=False,
                       contentContainerStyle=styles.strip, style=styles.stripScroll) if imgs else None

    def tile(tool):
        return Pressable(
            View(Feather(name=tool["icon"], size=22, color="#fff"), style=[styles.tileIcon, {"linearGradient": {"angle": 135, "colors": tool["colors"]}}]),
            Text(tool["title"], style=styles.tileTitle),
            Text(tool["sub"], style=styles.tileSub),
            onPress=open_tool(tool), style=styles.tile)

    header = View(Text("ImageKit", style=styles.brand),
                  Text("Compress, resize and clean photos. 100% on-device.", style=styles.tagline))
    tools = VStack(
        Text("Tools", style=styles.sectionTitle),
        # 2 tiles a row on phones, 3 on tablets; on desktop the tools sit beside the hero, so 2 again then 3 on xl.
        Grid(*[tile(x) for x in TOOLS], columns={"base": 2, "md": 3, "lg": 2, "xl": 3}, gap=14),
        spacing=12)

    # Phone/tablet: one column (header, hero, tools). Desktop (lg+): hero column left, tools right.
    return ScrollView(
        Container(GridRow(
            Col(VStack(header, hero, strip, spacing=16), span={"base": 12, "lg": 5}),
            Col(tools, span={"base": 12, "lg": 7}),
            gutter={"base": 20, "lg": 40}, align="flex-start"), padding=20),
        style=styles.screen,
        contentContainerStyle=styles.content)


default = Home


styles = StyleSheet.create(lambda theme, rt: {
    "screen": {"flex": 1, "backgroundColor": theme.colors.bg},
    "content": {"paddingTop": rt.insets.top + 16, "paddingBottom": rt.insets.bottom + 24},

    # Header
    "brand": {"fontSize": {"base": 34, "lg": 44}, "fontWeight": "800", "color": theme.colors.text},
    "tagline": {"fontSize": {"base": 14, "lg": 16}, "color": theme.colors.sub, "marginTop": 4},

    # Hero (choose photos)
    "hero": {"flexDirection": "row", "alignItems": "center", "gap": 14, "padding": 18, "borderRadius": 24,
             "linearGradient": {"angle": 120, "colors": [theme.colors.accent, theme.colors.accent2]}, **shadow(theme, 0.25)},
    "heroIcon": {"width": 56, "height": 56, "borderRadius": 18, "backgroundColor": "rgba(255,255,255,0.22)",
                 "alignItems": "center", "justifyContent": "center"},
    "heroText": {"flex": 1},
    "heroTitle": {"fontSize": 20, "fontWeight": "800", "color": "#fff"},
    "heroSub": {"fontSize": 13, "color": "rgba(255,255,255,0.85)", "marginTop": 2},

    # Selected photos strip
    "strip": {"gap": 10},
    "stripScroll": {"flexGrow": 0},

    # Tools grid
    "sectionTitle": {"fontSize": 18, "fontWeight": "700", "color": theme.colors.text},
    "tile": {"flexGrow": 1, "backgroundColor": theme.colors.card, "borderRadius": 20, "padding": 16, **shadow(theme, 0.06)},
    "tileIcon": {"width": 44, "height": 44, "borderRadius": 14, "alignItems": "center", "justifyContent": "center"},
    "tileTitle": {"fontSize": 15, "fontWeight": "700", "color": theme.colors.text, "marginTop": 12},
    "tileSub": {"fontSize": 12, "color": theme.colors.sub, "marginTop": 2},
})
