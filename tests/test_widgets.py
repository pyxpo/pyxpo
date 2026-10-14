from __future__ import annotations

from pyxpo import (Alert, Chip, Dropdown, Icon, InputField, LabeledCheckbox, MultiSelect, NumberInput, PasswordInput,
                   RadioGroup, SearchInput, Stepper, TabBar, TextArea, ThemeProvider)

from .test_core import mount


def _texts(r):
    return [n.props.get("text") for n in r.nodes.values() if n.type == "Text"]


def test_all_widgets_render():
    opts = [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}]
    app, r = mount(lambda: ThemeProvider(
        InputField(label="Name", placeholder="Your name", error="bad"),
        PasswordInput(label="Pw", value="x"), SearchInput(placeholder="Find"),
        TextArea(placeholder="Notes"), Dropdown(label="D", options=opts, value="a"),
        MultiSelect(label="M", options=opts, value=["a", "b"]), NumberInput(value=3),
        RadioGroup(options=opts, value="a"), Stepper(steps=["One", "Two", "Three"], current=1),
        Alert(message="careful", tone="warning"), LabeledCheckbox(label="Agree", value=True),
        Chip("tag"), Icon("search"),
        TabBar(tabs=[{"key": "h", "label": "Home", "icon": "home"}], value="h"),
    ))
    t = _texts(r)
    for want in ("Name", "bad", "A", "One", "Three", "careful", "Agree", "tag", "Home"):
        assert want in t, want


def test_multiselect_toggle_and_numberinput():
    got = []
    opts = [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}]
    app, r = mount(lambda: ThemeProvider(MultiSelect(options=opts, value=["a"], on_change=got.append)))
    assert "A" in _texts(r)
    n = []
    app, r = mount(lambda: ThemeProvider(NumberInput(value=3, on_change=n.append, minimum=0, maximum=5)))
    assert "3" in _texts(r)
