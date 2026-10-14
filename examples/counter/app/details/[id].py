from pyxpo import Button, Text, View
from pyxpo.router import router, useLocalSearchParams


def Details():
    params = useLocalSearchParams()
    return View(
        Text("Count was ", params["id"]),
        Button(title="Back", onPress=router.back),
        style={"flex": 1, "alignItems": "center", "justifyContent": "center"},
    )


default = Details
