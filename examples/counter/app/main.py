from pyxpo import Button, Text, View, component, run_app, use_state


@component
def Counter():
    n, set_n = use_state(0)
    return View(Text("Count: ", n), Button("Add", on_press=lambda: set_n(lambda c: c + 1)))


if __name__ == "__main__":
    run_app(Counter)
