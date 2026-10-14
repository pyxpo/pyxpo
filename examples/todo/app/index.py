from pyxpo import Button, Text, TextInput, View, useState


def Todo():
    items, setItems = useState([])
    draft, setDraft = useState("")

    def add():
        if draft:
            setItems(items + [draft])
            setDraft("")

    return View(
        TextInput(value=draft, onChangeText=setDraft, placeholder="New item"),
        Button(title="Add", onPress=add),
        *[Text(t, key="%d:%s" % (i, t)) for i, t in enumerate(items)],
        style={"flex": 1, "padding": 16},
    )


default = Todo
