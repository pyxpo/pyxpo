from __future__ import annotations

import pytest

from pyxpo import (FlatList, Image, Pressable, ScrollView, Slider, Switch, Text, TextInput, View, component, memo)

from .test_core import mount


def test_view_onPress_converted():
    f = lambda: None
    el = View(onPress=f)
    assert el.props["on_press"] is f and "onPress" not in el.props


def test_textinput_rn_names():
    el = TextInput(onChangeText=print, placeholderTextColor="#999", secureTextEntry=True, returnKeyType="done",
                   keyboardType="email-address", autoCapitalize="none", maxLength=5)
    p = el.props
    assert p["on_change_text"] is print and p["placeholder_color"] == "#999" and p["secure"] is True
    assert p["return_key"] == "done" and p["keyboard_type"] == "email-address" and p["max_length"] == 5


def test_flatlist_rn_names():
    app, r = mount(lambda: FlatList(data=[1, 2], renderItem=lambda info: Text(str(info["item"])),
                                    keyExtractor=lambda it, i: str(it), contentContainerStyle={"padding": 4}))
    assert "1" in r.texts() and "2" in r.texts()


def test_switch_trackColor_bool_keys():
    app, r = mount(lambda: Switch(value=True, onValueChange=lambda v: None, trackColor={False: "#111", True: "#222"}))
    n = r.find_all("NativeSwitch")[0]
    assert n.props["track_on"] != n.props["track_off"]


def test_slider_minimumValue():
    app, r = mount(lambda: Slider(value=5, minimumValue=0, maximumValue=10))
    n = r.find_all("NativeSlider")[0]
    assert n.props["maximum"] == 10.0


def test_text_numberOfLines_moves_to_style():
    el = Text("x", numberOfLines=2)
    from pyxpo.style import normalize
    assert normalize(el.props["style"])["number_of_lines"] == 2 and "number_of_lines" not in el.props


def test_both_spellings_raise():
    with pytest.raises(TypeError):
        View(onPress=1, on_press=2)


def test_scrollview_and_image_alias():
    el = ScrollView(contentContainerStyle={"padding": 1}, showsVerticalScrollIndicator=False)
    assert el.props["shows_vertical_scroll_indicator"] is False and "contentContainerStyle" not in el.props
    assert Image(source="asset:x", testID="i").props["test_id"] == "i"


def test_user_component_camel_param_untouched():
    seen = {}

    @component
    def Card(onPress=None):
        seen["p"] = onPress
        return View()

    f = lambda: None
    mount(lambda: Card(onPress=f))
    assert seen["p"] is f


def test_user_component_snake_param_accepts_camel():
    seen = {}

    @component
    def Card(on_press=None, title=""):
        seen["p"] = on_press
        return View()

    f = lambda: None
    mount(lambda: Card(onPress=f, title="t"))
    assert seen["p"] is f


def test_user_component_unknown_camel_kept_for_kwargs():
    seen = {}

    @component
    def Card(**props):
        seen.update(props)
        return View()

    mount(lambda: Card(someProp=1))
    assert seen == {"someProp": 1}


def test_memo_preserves_alias():
    seen = []

    @component
    def Row(on_press=None):
        seen.append(on_press)
        return View()

    M = memo(Row)
    f = lambda: None
    mount(lambda: M(onPress=f))
    assert seen == [f]


def test_key_not_aliased():
    assert View(key="k").key == "k"


def test_snake_spelling_of_renamed_rn_prop():
    # `secure_text_entry` is what a Python author writes; native reads `secure` (a password field before this)
    e = TextInput(secure_text_entry=True, placeholder_text_color="#888", return_key_type="go", keyboard_type="numeric")
    assert e.props == {"secure": True, "placeholder_color": "#888", "return_key": "go", "keyboard_type": "numeric"}
    with pytest.raises(TypeError):
        TextInput(secure=True, secure_text_entry=True)
