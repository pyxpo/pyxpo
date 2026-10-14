from __future__ import annotations

import pytest

from pyxpo import Stack, Tabs, Text, component, use_navigation, use_state

from .test_core import mount


def test_stack_push_pop_and_params():
    box = {}

    def Home(navigation, params):
        box["home"] = navigation
        return Text("home")

    def Detail(navigation, params):
        box["detail"] = navigation
        return Text("detail %s" % params.get("id"))

    app, r = mount(lambda: Stack(screens={"Home": Home, "Detail": Detail}, initial="Home", animate=False))
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

    app, r = mount(lambda: Stack(screens={"Home": Home, "Detail": Detail}, animate=False))
    box["n"].navigate("Detail")
    back = [n for n in r.root.walk() if n.props.get("accessibility_label") == "Back"]
    assert len(back) == 1
    r.press(back[0])
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


def test_stack_screens_toggle_empty_keeps_hook_order():
    box = {}

    @component
    def App():
        on, set_on = use_state(False)
        box["set"] = set_on
        return Stack(screens={"Home": lambda navigation, params: Text("home")} if on else {})

    app, r = mount(App)
    box["set"](True)
    assert "home" in r.texts()
    box["set"](False)
    assert "home" not in r.texts()
    box["set"](True)
    assert "home" in r.texts()


def test_use_navigation_sees_own_route_in_stack():
    seen = {}

    @component
    def Probe(tag=""):
        seen[tag] = use_navigation()
        return Text(tag)

    def Home(navigation, params):
        return Probe(tag="home")

    def Detail(navigation, params):
        return Probe(tag="detail")

    app, r = mount(lambda: Stack(screens={"Home": Home, "Detail": Detail}))
    seen["home"].navigate("Detail", id=3)
    # Home is re-rendered below the top; its descendants must still see the Home route.
    assert seen["home"].name == "Home"
    assert seen["detail"].name == "Detail" and seen["detail"].params == {"id": 3}
    seen["detail"].set_params(id=4)
    assert seen["detail"].params == {"id": 4}


def test_stack_screen_removed_while_on_stack():
    box = {}

    def Home(navigation, params):
        box["n"] = navigation
        return Text("home")

    @component
    def App():
        full, set_full = use_state(True)
        box["set"] = set_full
        screens = {"Home": Home, "Detail": lambda navigation, params: Text("detail")}
        if not full:
            del screens["Detail"]
        return Stack(screens=screens)

    app, r = mount(App)
    box["n"].navigate("Detail")
    box["set"](False)
    assert "home" in r.texts() and "detail" not in r.texts()


def test_tabs_navigation_switches_and_validates():
    seen = {}

    @component
    def Probe(tag=""):
        seen[tag] = use_navigation()
        return Text(tag)

    def A(navigation, params):
        seen["a_nav"] = navigation
        return Probe(tag="a")

    def B(navigation, params):
        return Probe(tag="b")

    app, r = mount(lambda: Tabs(screens={"A": A, "B": B}))
    with pytest.raises(KeyError):
        seen["a_nav"].navigate("Nope")
    assert "a" in r.texts()
    seen["a_nav"].navigate("B")
    assert "b" in r.texts()
    assert seen["a"].name == "A" and seen["b"].name == "B"
    seen["b"].reset("A")
    tab_a = r.find_text("A").parent
    assert tab_a.props["accessibility_state"] == {"selected": True}


def test_tabs_screens_toggle_empty_keeps_hook_order():
    box = {}

    @component
    def App():
        on, set_on = use_state(False)
        box["set"] = set_on
        return Tabs(screens={"A": lambda navigation, params: Text("a")} if on else {})

    app, r = mount(App)
    box["set"](True)
    assert "a" in r.texts()


def test_stack_native_swipe_back_event_pops():
    box = {}

    def Home(navigation, params):
        box["n"] = navigation
        return Text("home")

    app, r = mount(lambda: Stack(screens={"Home": Home, "Detail": lambda navigation, params: Text("detail")}))
    host = r.find_all("NavStack")[0]
    assert host.props["gesture"] is False
    box["n"].navigate("Detail")
    assert "detail" in r.texts() and host.props["gesture"] is True
    r.emit("pop_gesture", host)  # native finished an edge swipe
    assert "detail" not in r.texts()


def test_navigate_bubbles_to_parent_navigator():
    box = {}

    def Inner(navigation, params):
        box["inner"] = navigation
        return Text("inner")

    def Outer(navigation, params):
        return Stack(screens={"Inner": Inner}, animate=False)

    app, r = mount(lambda: Stack(screens={"Outer": Outer, "Other": lambda navigation, params: Text("other")},
                                 animate=False))
    assert box["inner"].parent is not None
    box["inner"].navigate("Other")
    assert "other" in r.texts()


def test_drawer_open_close_select():
    from pyxpo import Drawer
    box = {}

    def A(navigation, params):
        box["n"] = navigation
        return Text("page a")

    app, r = mount(lambda: Drawer(screens={"A": A, "B": lambda navigation, params: Text("page b")}))
    assert "page a" in r.texts() and "A" in r.texts()
    box["n"].open_drawer()
    assert r.find_text("B") is not None  # drawer item listed
    r.press(r.find_text("B").parent)
    assert "page b" in r.texts()
    box["n"].toggle_drawer()
    assert r.find_text("A") is not None


def test_top_tabs_lazy_mount_and_switch():
    from pyxpo import TopTabs
    box = {}

    def A(navigation, params):
        box["n"] = navigation
        return Text("page a")

    app, r = mount(lambda: TopTabs(screens={"A": A, "B": lambda navigation, params: Text("page b")}))
    assert "page b" not in r.texts()
    box["n"].navigate("B")
    assert "page b" in r.texts()


def test_statusbar_set_style_dedupes(monkeypatch):
    from pyxpo import modules
    calls = []
    monkeypatch.setattr(modules, "_app", object())
    monkeypatch.setattr(modules, "call", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(modules.StatusBar, "_style", None)
    modules.StatusBar.set_style("light")
    modules.StatusBar.set_style("light")
    modules.StatusBar.set_style("dark")
    assert calls == [("StatusBar", "set_style", "light"), ("StatusBar", "set_style", "dark")]
