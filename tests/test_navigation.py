from __future__ import annotations

import pytest

from pyxpo import Stack, Tabs, Text, use_navigation

from .test_core import mount


def test_stack_push_pop_and_params():
    box = {}

    def Home(navigation, params):
        box["home"] = navigation
        return Text("home")

    def Detail(navigation, params):
        box["detail"] = navigation
        return Text("detail %s" % params.get("id"))

    app, r = mount(lambda: Stack(screens={"Home": Home, "Detail": Detail}, initial="Home"))
    assert "home" in r.texts() and "detail 7" not in r.texts()
    box["home"].navigate("Detail", id=7)
    assert "detail 7" in r.texts()
    assert box["detail"].can_go_back()
    box["detail"].go_back()
    assert "detail 7" not in r.texts()
    assert not box["home"].can_go_back()


def test_stack_header_back_button():
    box = {}

    def Home(navigation, params):
        box["n"] = navigation
        return Text("home")

    def Detail(navigation, params):
        return Text("detail")

    app, r = mount(lambda: Stack(screens={"Home": Home, "Detail": Detail}))
    box["n"].navigate("Detail")
    r.press(r.find_text("‹").parent)
    assert "detail" not in r.texts()


def test_stack_replace_reset():
    box = {}

    def A(navigation, params):
        box["n"] = navigation
        return Text("a")

    def B(navigation, params):
        box["b"] = navigation
        return Text("b")

    app, r = mount(lambda: Stack(screens={"A": A, "B": B}))
    box["n"].navigate("B")
    box["b"].replace("A")
    assert "b" not in r.texts()
    box["n"].reset("B")
    assert "a" not in r.texts() and "b" in r.texts()


def test_stack_unknown_screen_raises():
    box = {}

    def Home(navigation, params):
        box["n"] = navigation
        return Text("h")

    mount(lambda: Stack(screens={"Home": Home}))
    with pytest.raises(KeyError):
        box["n"].navigate("Nope")


def test_tabs_lazy_mount():
    mounted = []

    def A(navigation, params):
        mounted.append("A")
        return Text("a")

    def B(navigation, params):
        mounted.append("B")
        return Text("b")

    app, r = mount(lambda: Tabs(screens={"A": A, "B": B}))
    assert mounted == ["A"]
    r.press(r.find_text("B").parent)
    assert "B" in mounted and "b" in r.texts()
