from pyxpo import component
from pyxpo.router import Stack


@component
def RootLayout():
    return Stack(
        Stack.Screen(name="index", options={"headerShown": False}),
        Stack.Screen(name="tool/[id]", options={"headerShown": False}),
        Stack.Screen(name="result", options={"headerShown": False}),
    )


default = RootLayout
