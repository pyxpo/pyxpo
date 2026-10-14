from pyxpo.router import Stack


def RootLayout():
    return Stack(
        Stack.Screen(name="index", options={"title": "Counter"}),
        Stack.Screen(name="details/[id]", options={"title": "Details"}),
    )


default = RootLayout
