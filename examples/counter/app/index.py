from pyxpo import Button, Text, View, useState
from pyxpo.router import Link


def Index():
    n, setN = useState(0)
    return View(
        Text("Count: ", n),
        Button(title="Add", onPress=lambda: setN(lambda c: c + 1)),
        Link("Open details", href="/details/%d" % n),
        style={"flex": 1, "alignItems": "center", "justifyContent": "center"},
    )


default = Index
