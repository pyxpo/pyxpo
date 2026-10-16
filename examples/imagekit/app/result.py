from pyxpo import Image, Text, View, component, useState
from pyxpo.apis import _bridge
from pyxpo_media_library import MediaLibrary
from pyxpo_sharing import Share

from app._store import useStore
from app._theme import TOOL, fmt_bytes, useTheme
from app._ui import Button, Card, Screen


@component
def Result():
    t, st = useTheme(), useStore()
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
        Text("%s%d%%" % ("-" if pct >= 0 else "+", abs(pct)), style={"fontSize": 44, "fontWeight": "800", "color": t["good"] if pct >= 0 else t["bad"]}),
        Text("%s → %s" % (fmt_bytes(saved), fmt_bytes(after)), style={"fontSize": 16, "fontWeight": "600", "color": t["text"]}),
        Text("Metadata removed · saved on device only", style={"fontSize": 12, "color": t["sub"]}),
        style={"alignItems": "center"})

    def card(r):
        o, s = r["out"], r["src"]
        return Card(
            Image(source=o["uri"], resizeMode="contain", style={"width": "100%", "height": 240, "borderRadius": 14, "backgroundColor": t["line"]}),
            View(Text("Before  %d × %d · %s" % (s["width"], s["height"], fmt_bytes(s["fileSize"])), style={"fontSize": 12, "color": t["sub"]}),
                 Text("After  %d × %d · %s" % (o["width"], o["height"], fmt_bytes(o["fileSize"])), style={"fontSize": 13, "fontWeight": "700", "color": t["text"]}), style={"gap": 2}))

    footer = View(Text(status, style={"fontSize": 13, "color": t["sub"], "marginBottom": 8}) if status else None,
                  View(View(Button("Save", save, icon="download", busy=busy), style={"flex": 1}),
                       View(Button("Share", share, icon="share", kind="secondary"), style={"flex": 1}), style={"flexDirection": "row", "gap": 12}))
    return Screen(summary, *[card(r) for r in res], title="Result" if not st["tool"] else TOOL[st["tool"]]["title"] + " done", footer=footer)


default = Result
