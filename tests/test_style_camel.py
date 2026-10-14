from __future__ import annotations

import copy
import pickle

import pytest

from pyxpo.style import StyleSheet, normalize, normalize_shared
from pyxpo._keys import to_snake


def test_to_snake_table():
    assert to_snake("fontSize") == "font_size"
    assert to_snake("borderTopLeftRadius") == "border_top_left_radius"
    assert to_snake("testID") == "test_id"
    assert to_snake("font_size") == "font_size"
    assert to_snake("ListHeaderComponent") == "list_header_component"
    assert to_snake("width") == "width"


def test_camel_keys_normalize_like_snake():
    camel = {"flex": 1, "backgroundColor": "#fff", "alignItems": "center", "justifyContent": "center",
             "padding": 20, "fontSize": 24, "fontWeight": "bold", "marginBottom": 10}
    snake = {"flex": 1, "background_color": "#fff", "align_items": "center", "justify_content": "center",
             "padding": 20, "font_size": 24, "font_weight": "bold", "margin_bottom": 10}
    assert normalize(camel) == normalize(snake)


def test_camel_shorthands_expand():
    n = normalize({"marginHorizontal": 4, "paddingVertical": 2, "borderRadius": 8})
    assert n["margin_left"] == n["margin_right"] == 4
    assert n["padding_top"] == n["padding_bottom"] == 2
    assert n["border_top_left_radius"] == 8


def test_specific_beats_shorthand_regardless_of_spelling():
    assert normalize({"marginTop": 1, "margin": 5})["margin_top"] == 1


def test_collision_across_list_later_wins():
    assert normalize([{"fontSize": 10}, {"font_size": 12}])["font_size"] == 12
    assert normalize([{"font_size": 10}, {"fontSize": 12}])["font_size"] == 12


def test_transform_items_camel():
    n = normalize({"transform": [{"translateY": 10}, {"scaleX": 2}]})
    assert n["translate_y"] == 10 and n["scale_x"] == 2


def test_shadow_offset_dict():
    n = normalize({"shadowOffset": {"width": 1, "height": 3}})
    assert n["shadow_offset_x"] == 1 and n["shadow_offset_y"] == 3 and "shadow_offset" not in n


def test_rotate_deg_string():
    assert normalize({"rotate": "45deg"})["rotate"] == 45.0
    assert abs(normalize({"rotate": "3.141592653589793rad"})["rotate"] - 180) < 1e-6


def test_cache_hit_identity_for_camel_and_nested():
    s = {"fontSize": 5, "transform": [{"scale": 2}]}
    assert normalize_shared(s) is normalize_shared(dict(s))


def test_nested_value_types_not_conflated():
    a = normalize_shared({"transform": [{"scale": 1}]})
    b = normalize_shared({"transform": [{"scale": True}]})
    assert a is not b


def test_animated_in_transform_not_cached():
    from pyxpo import Animated
    v = Animated.Value(1)
    s = {"transform": [{"scale": v}]}
    assert normalize_shared(s) is not normalize_shared(s)


def test_stylesheet_attr_and_item_access():
    styles = StyleSheet.create({"title": {"fontSize": 24}})
    assert styles.title is styles["title"]
    with pytest.raises(AttributeError):
        styles.nope


def test_stylesheet_is_dict_and_copyable():
    styles = StyleSheet.create({"a": {"fontSize": 1}})
    assert isinstance(styles, dict)
    assert copy.deepcopy(styles) == styles
    assert pickle.loads(pickle.dumps(styles)) == styles
    assert dict(**styles) == {"a": {"fontSize": 1}}


def test_compose_none_and_aliases():
    assert StyleSheet.compose(None, {"a": 1}) == {"a": 1}
    assert StyleSheet.compose({"a": 1}, False) == {"a": 1}
    assert StyleSheet.compose({"a": 1}, {"b": 2}) == [{"a": 1}, {"b": 2}]
    assert StyleSheet.absoluteFill is StyleSheet.absolute_fill
    assert StyleSheet.hairlineWidth == StyleSheet.hairline_width


def test_unknown_and_unsupported_key_warn_once(capfd):
    from pyxpo import style as st
    st._warned.clear()
    normalize({"bogusKey": 1, "tintColor": "#fff"}, warn=True)
    normalize({"bogusKey": 1}, warn=True)
    err = capfd.readouterr().err
    assert err.count("bogus_key") == 1 and "tint_color" in err and "not supported" in err


def test_user_home_example_reaches_wire():
    from pyxpo import Text, View
    from .test_core import mount
    styles = StyleSheet.create({"container": {"flex": 1, "alignItems": "center", "padding": 20},
                                "title": {"fontSize": 24, "fontWeight": "bold", "color": "#333"}})
    app, r = mount(lambda: View(Text("Welcome", style=styles.title), style=styles.container))
    t = r.find_text("Welcome")
    assert t.props["style"]["font_size"] == 24
    assert t.parent.props["style"]["align_items"] == "center"
