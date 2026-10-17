from pyxpo import Grid, Image, Text, View, StyleSheet, component, useState
from pyxpo.apis import _bridge
from pyxpo_media_library import MediaLibrary
from pyxpo_sharing import Share

from app._store import useStore
from app._theme import TOOL, fmt_bytes
from app._ui import Button, Card, Screen


@component
def Result():
    st = useStore()
    res = st["results"]
    status, setStatus = useState("")
    busy, setBusy = useState(False)
    saved = sum(r["src"]["fileSize"] for r in res)
    after = sum(r["out"]["fileSize"] for r in res)
    pct = int(round(100.0 * (saved - after) / saved)) if saved else 0

    def save():
        setBusy(True)

        async def go():
            try:
                perm = await MediaLibrary.requestPermissionsAsync(writeOnly=True)
                if not perm.get("granted"):
                    setStatus("Photos permission denied")
                    return
                for r in res:
                    await MediaLibrary.saveToLibraryAsync(r["out"]["uri"])
                setStatus("Saved %d photo%s to your library" % (len(res), "" if len(res) == 1 else "s"))
            except Exception as e:  # noqa: BLE001
                setStatus("Save failed: %s" % e)
            finally:
                setBusy(False)
        _bridge.spawn(go())

    def share():
        async def go():
            try:
                await Share.share({"urls": [r["out"]["uri"] for r in res]})
            except Exception as e:  # noqa: BLE001
                setStatus("Share failed: %s" % e)
        _bridge.spawn(go())

    summary = Card(
        Text("%s%d%%" % ("-" if pct >= 0 else "+", abs(pct)), style=[styles.percent, pct < 0 and styles.percentWorse]),
        Text("%s → %s" % (fmt_bytes(saved), fmt_bytes(after)), style=styles.sizes),
        Text("Metadata removed · saved on device only", style=styles.note),
        style=styles.summary)

    def card(r):
        o, src = r["out"], r["src"]
        return Card(
            Image(source=o["uri"], resizeMode="contain", style=styles.preview),
            View(Text("Before  %d × %d · %s" % (src["width"], src["height"], fmt_bytes(src["fileSize"])), style=styles.before),
                 Text("After  %d × %d · %s" % (o["width"], o["height"], fmt_bytes(o["fileSize"])), style=styles.after), style=styles.meta),
            style=styles.resultCard)

    footer = View(Text(status, style=styles.status) if status else None,
                  View(View(Button("Save", save, icon="download", busy=busy), style=styles.action),
                       View(Button("Share", share, icon="share", kind="secondary"), style=styles.action), style=styles.actions))
    # One result card a row on phones, 2 on tablets, 3 on wide desktops.
    cards = Grid(*[card(r) for r in res], columns={"base": 1, "md": 2, "xl": 3}, gap=16)
    return Screen(summary, cards, title="Result" if not st["tool"] else TOOL[st["tool"]]["title"] + " done", footer=footer)


default = Result


styles = StyleSheet.create(lambda theme, rt: {
    # Summary card
    "summary": {"alignItems": "center"},
    "percent": {"fontSize": 44, "fontWeight": "800", "color": theme.colors.good},
    "percentWorse": {"color": theme.colors.bad},
    "sizes": {"fontSize": 16, "fontWeight": "600", "color": theme.colors.text},
    "note": {"fontSize": 12, "color": theme.colors.sub},

    # Result card
    "resultCard": {"flexGrow": 1},
    "preview": {"width": "100%", "height": 240, "borderRadius": 14, "backgroundColor": theme.colors.line},
    "meta": {"gap": 2},
    "before": {"fontSize": 12, "color": theme.colors.sub},
    "after": {"fontSize": 13, "fontWeight": "700", "color": theme.colors.text},

    # Footer
    "status": {"fontSize": 13, "color": theme.colors.sub, "marginBottom": 8},
    "actions": {"flexDirection": "row", "gap": 12},
    "action": {"flex": 1},
})
