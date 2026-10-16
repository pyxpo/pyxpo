from pyxpo import Pressable, ScrollView, Text, View, component, useEffect, useSafeAreaInsets
from pyxpo.router import router
from pyxpo.apis import _bridge
from pyxpo.vector_icons import Feather

from app import _boot
from app._store import pick, update, useStore
from app._theme import TOOLS, fmt_bytes, useTheme
from app._ui import Card, Thumb, shadow


@component
def Home():
    t, insets, st = useTheme(), useSafeAreaInsets(), useStore()
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
        View(Feather(name="image", size=30, color="#fff"), style={"width": 56, "height": 56, "borderRadius": 18, "backgroundColor": "rgba(255,255,255,0.22)", "alignItems": "center", "justifyContent": "center"}),
        View(Text("Choose photos" if not imgs else "%d photo%s selected" % (len(imgs), "" if len(imgs) == 1 else "s"), style={"fontSize": 20, "fontWeight": "800", "color": "#fff"}),
             Text("From your library · stays on this device" if not imgs else "Tap to change · %s total" % fmt_bytes(sum(i.get("fileSize") or 0 for i in imgs)), style={"fontSize": 13, "color": "rgba(255,255,255,0.85)", "marginTop": 2}),
             style={"flex": 1}),
        Feather(name="chevron-right", size=22, color="#fff"),
        onPress=choose,
        style={"flexDirection": "row", "alignItems": "center", "gap": 14, "padding": 18, "borderRadius": 24,
               "linearGradient": {"angle": 120, "colors": [t["accent"], t["accent2"]]}, **shadow(t, 0.25)})

    strip = ScrollView(*[Thumb(i["uri"], 64, 14) for i in imgs], horizontal=True, showsHorizontalScrollIndicator=False,
                       contentContainerStyle={"gap": 10}, style={"flexGrow": 0}) if imgs else None

    def tile(tool):
        return Pressable(
            View(Feather(name=tool["icon"], size=22, color="#fff"), style={"width": 44, "height": 44, "borderRadius": 14, "alignItems": "center", "justifyContent": "center",
                                                                          "linearGradient": {"angle": 135, "colors": tool["colors"]}}),
            Text(tool["title"], style={"fontSize": 15, "fontWeight": "700", "color": t["text"], "marginTop": 12}),
            Text(tool["sub"], style={"fontSize": 12, "color": t["sub"], "marginTop": 2}),
            onPress=open_tool(tool),
            style={"width": "48%", "backgroundColor": t["card"], "borderRadius": 20, "padding": 16, **shadow(t, 0.06)})

    return ScrollView(
        View(Text("ImageKit", style={"fontSize": 34, "fontWeight": "800", "color": t["text"]}),
             Text("Compress, resize and clean photos. 100% on-device.", style={"fontSize": 14, "color": t["sub"], "marginTop": 4})),
        hero, strip,
        Text("Tools", style={"fontSize": 18, "fontWeight": "700", "color": t["text"], "marginTop": 8}),
        View(*[tile(x) for x in TOOLS], style={"flexDirection": "row", "flexWrap": "wrap", "justifyContent": "space-between", "rowGap": 14}),
        style={"flex": 1, "backgroundColor": t["bg"]},
        contentContainerStyle={"padding": 20, "gap": 16, "paddingTop": insets["top"] + 16, "paddingBottom": insets["bottom"] + 24})


default = Home
