"""React-Native-style pyxpo: camelCase props/styles, StyleSheet.create, RN hooks, FlatList renderItem({item, index})."""
from pyxpo import FlatList, Pressable, StyleSheet, Text, TextInput, View, useEffect, useState

styles = StyleSheet.create(
    container=dict(flex=1, padding=16, backgroundColor="#fff"),
    title=dict(fontSize=24, fontWeight="bold", marginBottom=12),
    input=dict(borderWidth=1, borderColor="#ccc", borderRadius=8, padding=10, marginBottom=8),
    button=dict(backgroundColor="#2563eb", padding=12, borderRadius=8, alignItems="center"),
    buttonText=dict(color="#fff", fontWeight="600"),
    row=dict(paddingVertical=10, borderBottomWidth=1, borderColor="#eee"),
)


def App():
    items, setItems = useState(["Buy milk", "Write code"])
    text, setText = useState("")

    useEffect(lambda: print("items:", len(items)), [items])

    def add():
        if text.strip():
            setItems(lambda cur: cur + [text.strip()])
            setText("")

    return View(
        Text("Todo", style=styles.title),
        TextInput(value=text, onChangeText=setText, placeholder="New item", style=styles.input),
        Pressable(Text("Add", style=styles.buttonText), onPress=add, style=styles.button),
        FlatList(data=items, renderItem=lambda p: View(Text(p["item"]), style=styles.row),
                 keyExtractor=lambda item, i: item),
        style=styles.container,
    )


default = App
