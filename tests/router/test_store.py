import os

import pytest

from pyxpo.router.discovery import discover
from pyxpo.router.store import Store

FILES = {
    "_layout.py": "", "index.py": "", "about.py": "", "+not-found.py": "", "user/[id].py": "",
    "(tabs)/_layout.py": "", "(tabs)/home.py": "",
    "(tabs)/settings/_layout.py": "", "(tabs)/settings/index.py": "", "(tabs)/settings/advanced.py": "",
}


@pytest.fixture
def tree(tmp_app):
    return discover(tmp_app(FILES))


def nav_path(tree, *names):
    nav = tree.root
    for n in names:
        nav = nav.screen(n).navigator
    return nav.path


def names(node):
    return [r["name"] for r in node["routes"]]


def register_all(store, tree):
    store.register_navigator(tree.root.path, "stack")
    store.register_navigator(nav_path(tree, "(tabs)"), "tabs", {"order": ["home", "settings"]})
    store.register_navigator(nav_path(tree, "(tabs)", "settings"), "stack", {"initialRouteName": "index"})


def test_stack_navigate_push_replace(tree):
    s = Store(tree)
    s.register_navigator(tree.root.path, "stack")
    calls = []
    s.subscribe(lambda: calls.append(1))
    s.navigate("/about")
    s.navigate("/about")                       # idempotent: no change, no notify
    assert names(s.state) == ["index", "about"] and len(calls) == 1
    s.push("/about")
    assert names(s.state) == ["index", "about", "about"]
    s.navigate("/")                            # pops to existing route below
    assert names(s.state) == ["index"] and s.state["index"] == 0
    s.navigate("/user/1")
    key = s.state["routes"][-1]["key"]
    s.navigate("/user/2")                      # same top name: params updated in place
    assert names(s.state) == ["index", "user/[id]"] and s.state["routes"][-1]["key"] == key
    assert s.params == {"id": "2"} and s.pathname == "/user/2"
    s.push("/user/3")
    assert names(s.state) == ["index", "user/[id]", "user/[id]"]
    s.replace("/about")
    assert names(s.state) == ["index", "user/[id]", "about"] and s.state["index"] == 2
    assert len({r["key"] for r in s.state["routes"]}) == 3


def test_deep_link_tabs_in_stack_and_back(tree):
    s = Store(tree, "/settings/advanced?x=1")
    chain = s.focused_chain()
    assert [n["type"] for n, _ in chain] == ["stack", "stack", "stack"]   # unregistered: provisional stacks
    register_all(s, tree)
    (root, tabs_r), (tabs, settings_r), (settings, leaf) = s.focused_chain()
    assert tabs["type"] == "tabs" and names(tabs) == ["home", "settings"] and tabs["index"] == 1
    assert "state" not in tabs["routes"][0]                              # unvisited tab is lazy
    assert names(settings) == ["index", "advanced"] and settings["index"] == 1
    assert s.pathname == "/settings/advanced" and s.segments == ["(tabs)", "settings", "advanced"]
    assert s.params == {"x": "1"}
    assert s.can_go_back() and s.back() and s.pathname == "/settings"
    assert s.back() and s.pathname == "/home"                             # firstRoute tab
    assert not s.can_go_back() and s.back() is False                     # root: caller exits


def test_registered_types_build_directly_and_unvisited_tab(tree):
    s = Store(tree)
    register_all(s, tree)
    s.navigate("/home")
    tabs = s.focused_chain()[1][0]
    assert names(s.state) == ["index", "(tabs)"] and tabs["type"] == "tabs" and tabs["index"] == 0
    s.navigate("/settings/advanced")                                      # inside an unvisited tab
    tabs, settings = s.focused_chain()[1][0], s.focused_chain()[2][0]
    assert tabs["index"] == 1 and names(settings) == ["index", "advanced"]
    s.navigate("/home")
    s.set_index(tabs["key"], 1)                                           # tab state kept across switches
    assert s.pathname == "/settings/advanced"
    s.navigate("/")                                                       # pops (tabs) off the root stack
    assert names(s.state) == ["index"]


def test_set_index_builds_initial_state(tree):
    s = Store(tree, "/home")
    register_all(s, tree)
    tabs = s.focused_chain()[1][0]
    s.set_index(tabs["key"], 1)
    assert s.pathname == "/settings" and s.segments == ["(tabs)", "settings"]
    s.set_index(tabs["key"], 9)                                           # out of range: ignored
    assert s.pathname == "/settings"


def test_initial_route_names_callable(tree):
    s = Store(tree, "/about", initial_route_names=lambda nav: "index" if nav is tree.root else None)
    assert names(s.state) == ["index", "about"] and s.back() and not s.can_go_back()


def test_dismiss_family(tree):
    s = Store(tree, "/settings/advanced")
    register_all(s, tree)
    s.push("/about")
    s.push("/user/1")
    s.push("/user/2")
    assert s.can_dismiss()
    s.dismiss(2)
    assert names(s.state) == ["(tabs)", "about"]
    s.dismiss_all()
    assert names(s.state) == ["(tabs)"] and s.pathname == "/settings/advanced"
    s.dismiss()                                                           # nearest stack is now the settings one
    assert s.pathname == "/settings" and not s.can_dismiss()
    s.push("/about")
    s.push("/user/5")
    s.dismiss_to("/about")
    assert names(s.state) == ["(tabs)", "about"]
    s.dismiss_to("/user/9")                                               # not in stack: replaces the top
    assert names(s.state) == ["(tabs)", "user/[id]"] and s.params == {"id": "9"}


def test_not_found(tree, tmp_app):
    s = Store(tree)
    s.navigate("/nope/x?q=1")
    assert names(s.state)[-1] == "+not-found" and s.pathname == "/nope/x"
    assert s.params["q"] == "1"
    os.remove(os.path.join(tmp_app({}), "+not-found.py"))
    s = Store(discover(tmp_app({})), "/zzz")
    assert names(s.state) == ["+not-found"] and s.segments == ["+not-found"] and s.pathname == "/zzz"


def test_focus_blur_and_batching(tree):
    s = Store(tree)
    log, calls = [], []
    s.subscribe(lambda: calls.append(1))
    first = s.state["routes"][0]["key"]
    s.add_listener(first, "blur", lambda: log.append("blur"))
    s.add_listener(first, "focus", lambda: log.append("focus"))
    with s.batch():
        s.navigate("/about")
        s.navigate("/user/1")
        assert calls == []
    assert len(calls) == 1 and log == ["blur"] and not s.is_focused(first)
    s.navigate("/")
    assert log == ["blur", "focus"] and s.is_focused(first)
    with s.batch():                                                       # blur+focus in one batch: no events
        s.navigate("/about")
        s.back()
    assert log == ["blur", "focus"] and len(calls) == 2
    unsub = s.subscribe(lambda: calls.append(2))
    unsub()
    s.navigate("/about")
    assert 2 not in calls


def test_params_helpers_and_relative(tree):
    s = Store(tree, "/user/7?tag=a&tag=b")
    leaf = s.focused_chain()[-1][1]["key"]
    assert s.params == {"id": "7", "tag": ["a", "b"]}
    s.set_params({"tag": None, "n": 3})
    assert s.route_params(leaf) == {"id": "7", "n": "3"}
    s.set_params({"z": "1"}, route_key="missing")
    assert s.route_params("missing") == {}
    s.navigate("../about")
    assert s.pathname == "/about"
    s.navigate({"pathname": "/user/[id]", "params": {"id": "a b"}})
    assert s.pathname == "/user/a%20b" and s.params == {"id": "a b"}


def test_pop_route_key(tree):
    s = Store(tree)
    s.push("/about")
    s.push("/user/1")
    s.pop(s.state["routes"][1]["key"])
    assert names(s.state) == ["index"]
    s.pop(s.state["routes"][0]["key"])                                    # cannot pop the stack root
    assert names(s.state) == ["index"]


def test_drawer_and_slot(tree, tmp_app):
    s = Store(tree, "/home")
    s.register_navigator(nav_path(tree, "(tabs)"), "drawer")
    drawer = s.focused_chain()[1][0]
    assert drawer["type"] == "drawer" and drawer["drawer_open"] is False
    s.set_drawer_open(drawer["key"], True)
    assert s.focused_chain()[1][0]["drawer_open"] and s.back()          # back closes the drawer first
    assert s.focused_chain()[1][0]["drawer_open"] is False
    s.set_drawer_open(drawer["key"], True)
    s.navigate("/settings")                                               # navigating closes it
    assert s.focused_chain()[1][0]["drawer_open"] is False
    with pytest.raises(ValueError):
        s.register_navigator(tree.root.path, "modal")

    os.remove(os.path.join(tmp_app({}), "_layout.py"))
    s = Store(discover(tmp_app({})))                                      # no root layout: implicit Slot
    s.navigate("/about")
    assert s.state["type"] == "slot" and names(s.state) == ["about"] and not s.can_go_back()


def test_reregister_changes_type(tree):
    s = Store(tree, "/home")
    calls = []
    s.subscribe(lambda: calls.append(1))
    register_all(s, tree)
    n = len(calls)
    register_all(s, tree)                                                 # unchanged registration: no notify
    assert len(calls) == n
    s.register_navigator(nav_path(tree, "(tabs)"), "tabs", {"order": ["settings", "home"]})
    tabs = s.focused_chain()[1][0]
    assert names(tabs) == ["settings", "home"] and tabs["index"] == 1
    s.register_navigator(nav_path(tree, "(tabs)"), "slot")
    assert names(s.focused_chain()[1][0]) == ["home"]
