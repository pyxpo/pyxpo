from pyxpo import Button, Text, TextInput, View, component, run_app, use_state


@component
def Todo():
    items, set_items = use_state([])
    draft, set_draft = use_state("")

    def add():
        if draft:
            set_items(items + [draft])
            set_draft("")

    return View(
        TextInput(value=draft, on_change_text=set_draft),
        Button("Add", on_press=add),
        *[Text(t, key="%d:%s" % (i, t)) for i, t in enumerate(items)],
    )


if __name__ == "__main__":
    run_app(Todo)
