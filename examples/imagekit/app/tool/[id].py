import sys

from pyxpo import Keyboard, Text, TextInput, View, component, useEffect, useState
from pyxpo.apis import _bridge
from pyxpo.router import router, useLocalSearchParams

from app._store import update, useStore
from app._theme import TOOL, fmt_bytes, useTheme
from app._ui import Button, Card, Chip, Row, Screen, Thumb
from pyxpo_image_manipulator import ImageManipulator

from app import _ops

PRESETS = [("500 KB", 500 * 1024), ("1 MB", 1024 * 1024), ("2 MB", 2 * 1024 * 1024), ("5 MB", 5 * 1024 * 1024)]
RATIOS = ["1:1", "4:3", "3:4", "16:9", "9:16", "3:2"]
FORMATS = [("JPG", "jpeg"), ("PNG", "png")] + ([("HEIC", "heic")] if sys.platform == "ios" else [])


def num(s):
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return 0


@component
def ToolScreen():
    t, st = useTheme(), useStore()
    tool = TOOL.get(useLocalSearchParams().get("id"), TOOL["compress"])
    tid, imgs = tool["id"], st["images"]
    preset, setPreset = useState(1)
    custom, setCustom = useState("")
    w, setW = useState("")
    h, setH = useState("")
    ratio, setRatio = useState("1:1")
    fmt, setFmt = useState("jpeg")
    busy, setBusy = useState(False)
    err, setErr = useState("")
    infos, setInfos = useState([])

    def load():
        async def go():
            try:
                setInfos([await ImageManipulator.getInfoAsync(i["uri"]) for i in imgs])
            except Exception as e:  # noqa: BLE001
                setErr(str(e))
        _bridge.spawn(go())
    useEffect(load, [len(imgs)])

    def op(uri):
        if tid == "compress":
            kb = num(custom)
            return ImageManipulator.compressToSizeAsync(uri, kb * 1024 if preset < 0 else PRESETS[preset][1])
        if tid == "resize":
            return _ops.resize(uri, num(w), num(h))
        if tid == "convert":
            return _ops.convert(uri, fmt)
        if tid == "metadata":
            return _ops.strip_metadata(uri)
        if tid == "crop":
            return _ops.crop_ratio(uri, ratio)
        return _ops.optimize(uri)

    def run():
        Keyboard.dismiss()
        setErr("")
        setBusy(True)

        async def go():
            try:
                out = []
                for src, info in zip(imgs, infos):
                    out.append({"src": info, "out": await op(src["uri"])})
                update(results=out, tool=tid)
                router.push("/result")
            except Exception as e:  # noqa: BLE001
                setErr(str(e))
            finally:
                setBusy(False)
        _bridge.spawn(go())

    first = infos[0] if infos else None
    if first and not w and not h and tid == "resize":
        setW(str(first["width"]))
        setH(str(first["height"]))

    def field(label, value, on, ph, row=False):
        return View(Text(label, style={"fontSize": 12, "fontWeight": "600", "color": t["sub"], "marginBottom": 6}),
                    TextInput(value=value, onChangeText=on, placeholder=ph, keyboardType="number-pad",
                              style={"height": 48, "borderRadius": 14, "paddingHorizontal": 14, "fontSize": 16, "color": t["text"], "backgroundColor": t["chip"]}),
                    style={"flex": 1} if row else None)

    if tid == "compress":
        opts = Card(Text("Make it under…", style={"fontSize": 16, "fontWeight": "700", "color": t["text"]}),
                    View(*[Chip(n, preset == i, (lambda i=i: setPreset(i))) for i, (n, _) in enumerate(PRESETS)] + [Chip("Custom", preset < 0, lambda: setPreset(-1))],
                         style={"flexDirection": "row", "flexWrap": "wrap", "gap": 8}),
                    field("Custom size (KB)", custom, setCustom, "e.g. 250") if preset < 0 else None)
    elif tid == "resize":
        opts = Card(Text("Dimensions (px)", style={"fontSize": 16, "fontWeight": "700", "color": t["text"]}),
                    View(field("Width", w, setW, "auto", True), field("Height", h, setH, "auto", True), style={"flexDirection": "row", "gap": 12}),
                    Text("Fill both for an exact size. Leave one empty to keep the aspect ratio.", style={"fontSize": 12, "color": t["sub"]}))
    elif tid == "convert":
        opts = Card(Text("Convert to", style={"fontSize": 16, "fontWeight": "700", "color": t["text"]}),
                    View(*[Chip(n, fmt == v, (lambda v=v: setFmt(v))) for n, v in FORMATS], style={"flexDirection": "row", "gap": 8}))
    elif tid == "crop":
        opts = Card(Text("Aspect ratio", style={"fontSize": 16, "fontWeight": "700", "color": t["text"]}),
                    View(*[Chip(r, ratio == r, (lambda r=r: setRatio(r))) for r in RATIOS], style={"flexDirection": "row", "flexWrap": "wrap", "gap": 8}),
                    Text("Centered crop of the largest area that fits.", style={"fontSize": 12, "color": t["sub"]}))
    elif tid == "info":
        opts = None
    else:
        opts = Card(Text(tool["title"], style={"fontSize": 16, "fontWeight": "700", "color": t["text"]}),
                    Text("Long edge up to 2560 px, JPEG quality 80%. EXIF and GPS removed. Runs on every selected photo." if tid == "optimize"
                         else "Saves a clean copy with no EXIF or GPS data. Dimensions stay the same and the file never gets bigger.", style={"fontSize": 13, "color": t["sub"]}))

    def info_card(i, n):
        name = "Photo %d" % (n + 1)
        return Card(
            View(Thumb(i["uri"], 56, 12), View(Text(name, numberOfLines=1, style={"fontSize": 14, "fontWeight": "700", "color": t["text"]}),
                                               Text("%d × %d · %s" % (i["width"], i["height"], fmt_bytes(i["fileSize"])), style={"fontSize": 12, "color": t["sub"], "marginTop": 2}), style={"flex": 1}),
                 style={"flexDirection": "row", "gap": 12, "alignItems": "center"}),
            Row("Format", i["format"].upper()), Row("EXIF", "Yes" if i["hasExif"] else "No"), Row("GPS location", "Yes" if i["hasGps"] else "No")) \
            if tid == "info" else Card(
            View(Thumb(i["uri"], 56, 12), View(Text(name, numberOfLines=1, style={"fontSize": 14, "fontWeight": "700", "color": t["text"]}),
                                               Text("%d × %d · %s · %s" % (i["width"], i["height"], i["format"].upper(), fmt_bytes(i["fileSize"])), style={"fontSize": 12, "color": t["sub"], "marginTop": 2}), style={"flex": 1}),
                 style={"flexDirection": "row", "gap": 12, "alignItems": "center"}))

    footer = None if tid == "info" else View(
        Text(err, style={"color": t["bad"], "fontSize": 13, "marginBottom": 8}) if err else None,
        Button("Processing…" if busy else ("Apply to %d photo%s" % (len(imgs), "" if len(imgs) == 1 else "s")), run, icon="zap", busy=busy, disabled=not infos))
    return Screen(opts, Text("%d selected" % len(imgs), style={"fontSize": 13, "fontWeight": "600", "color": t["sub"]}), *[info_card(i, n) for n, i in enumerate(infos)],
                  title=tool["title"], footer=footer)


default = ToolScreen
