from pyxpo import LocalChannel, create_app
from pyxpo.renderers.mock import MockRenderer
from pyxpo.router.discovery import discover
from pyxpo.router.root import RouterRoot

LAYOUT = '''
from pyxpo.router import Stack
def L():
    return Stack(Stack.Screen(name="index", options={"title": "Home"}),
                 Stack.Screen(name="details/[id]", options={"title": "Details"}))
default = L
'''
INDEX = '''
from pyxpo import Text
from pyxpo.router import Link, router
def Index():
    return Link("Open", href="/details/7")
default = Index
'''
DETAILS = '''
from pyxpo import Text
from pyxpo.router import useLocalSearchParams
def D():
    p = useLocalSearchParams()
    return Text("id=" + str(p["id"]))
default = D
'''


def mount(app_dir, href="/"):
    ch = LocalChannel()
    r = MockRenderer(ch)
    app = create_app(RouterRoot, ch, tree=discover(app_dir), root_dir=app_dir, initial_href=href)
    return app, r


def test_stack_push_and_back(tmp_app):
    d = tmp_app({"_layout.py": LAYOUT, "index.py": INDEX, "details/[id].py": DETAILS})
    app, r = mount(d)
    assert "Home" in r.texts() and "Open" in r.texts()
    r.press(r.find_text("Open"))
    assert "id=7" in r.texts() and "Details" in r.texts()
    from pyxpo.router import router
    assert router.canGoBack() is True
    router.back()
    assert "id=7" not in r.texts()
    assert router.canGoBack() is False


def test_tabs_switch_and_lazy(tmp_app):
    d = tmp_app({
        "_layout.py": "from pyxpo.router import Tabs\ndef L():\n    return Tabs(Tabs.Screen(name='index', options={'title': 'Feed'}), Tabs.Screen(name='me', options={'title': 'Me'}))\ndefault = L\n",
        "index.py": "from pyxpo import Text\ndef P():\n    return Text('feed-page')\ndefault = P\n",
        "me.py": "from pyxpo import Text\ndef P():\n    return Text('me-page')\ndefault = P\n"})
    app, r = mount(d)
    assert "feed-page" in r.texts() and "me-page" not in r.texts()
    from pyxpo.router import router
    router.navigate("/me")
    assert "me-page" in r.texts()
    r.press(r.find_text("Feed"))
    assert "feed-page" in r.texts()


CUSTOM_BAR = """
from pyxpo import Pressable, Text, View
from pyxpo.router import Tabs
def bar(p):
    return View(*[Pressable(Text("[%s]" % it["label"] if i == p["index"] else it["label"]),
                            on_press=lambda i=i: p["on_select"](i)) for i, it in enumerate(p["items"])],
                Text("pos=" + p["position"]), test_id="bar")
def L():
    return Tabs(Tabs.Screen(name='index', options={'title': 'Feed'}), Tabs.Screen(name='me', options={'title': 'Me'}),
                screen_options={'tabBarPosition': 'left', 'headerShown': False}, tab_bar=bar)
default = L
"""


def test_tabs_custom_bar_on_the_start_side(tmp_app):
    d = tmp_app({"_layout.py": CUSTOM_BAR,
                 "index.py": "from pyxpo import Text\ndef P():\n    return Text('feed-page')\ndefault = P\n",
                 "me.py": "from pyxpo import Text\ndef P():\n    return Text('me-page')\ndefault = P\n"})
    app, r = mount(d)
    assert "[Feed]" in r.texts() and "pos=left" in r.texts()
    bar = next(n for n in r.root.walk() if n.props.get("test_id") == "bar")
    assert bar.parent.props["style"]["flex_direction"] == "row" and bar.parent.children[0] is bar
    r.press(r.find_text("Me"))
    assert "[Me]" in r.texts() and "me-page" in r.texts()


def test_tabs_rejects_unknown_position(tmp_app):
    d = tmp_app({"_layout.py": CUSTOM_BAR.replace("'left'", "'top'"),
                 "index.py": "from pyxpo import Text\ndef P():\n    return Text('x')\ndefault = P\n",
                 "me.py": "from pyxpo import Text\ndef P():\n    return Text('y')\ndefault = P\n"})
    app, r = mount(d)
    assert "tabBarPosition must be" in " ".join(r.texts())


def test_tabs_button_test_id(tmp_app):
    d = tmp_app({"_layout.py": "from pyxpo.router import Tabs\ndef L():\n    return Tabs(Tabs.Screen(name='index', options={'title': 'A', 'tabBarButtonTestID': 'tab-a'}))\ndefault = L\n",
                 "index.py": "from pyxpo import Text\ndef P():\n    return Text('a')\ndefault = P\n"})
    app, r = mount(d)
    assert any(n.props.get("test_id") == "tab-a" for n in r.root.walk())


def test_not_found_and_params_hooks(tmp_app):
    d = tmp_app({"_layout.py": LAYOUT, "index.py": INDEX, "details/[id].py": DETAILS})
    app, r = mount(d, "/nope/x")
    assert "Unmatched Route" in r.texts()


def test_drawer_open_close(tmp_app):
    d = tmp_app({
        "_layout.py": "from pyxpo.router import Drawer\ndef L():\n    return Drawer(Drawer.Screen(name='index', options={'title': 'Home'}), Drawer.Screen(name='b', options={'title': 'B'}))\ndefault = L\n",
        "index.py": "from pyxpo import Text\ndef P():\n    return Text('home-page')\ndefault = P\n",
        "b.py": "from pyxpo import Text\ndef P():\n    return Text('b-page')\ndefault = P\n"})
    app, r = mount(d)
    from pyxpo.router import router
    assert "home-page" in r.texts()
    from pyxpo.router.root import RouterRoot  # noqa: F401
    router._s.set_drawer_open(router._s.state["key"], True)
    r.advance(400)
    assert "B" in r.texts()
    router.navigate("/b")
    r.advance(400)
    assert "b-page" in r.texts()


def test_header_back_icon_is_vector_path_not_placeholder(tmp_app):
    d = tmp_app({"_layout.py": LAYOUT, "index.py": INDEX, "details/[id].py": DETAILS})
    app, r = mount(d)
    r.press(r.find_text("Open"))
    assert "?" not in r.texts()
    assert r.find_all("Path")


def test_deep_link_url_event_and_initial_url(tmp_app, monkeypatch):
    from pyxpo.router.root import href_from_url
    assert href_from_url("myapp://details/7?x=1") == "/details/7?x=1"
    assert href_from_url("myapp:///details/7") == "/details/7"
    assert href_from_url("https://h.io/details/7") == "/details/7"
    assert href_from_url("nope") is None
    d = tmp_app({"_layout.py": LAYOUT, "index.py": INDEX, "details/[id].py": DETAILS})
    app, r = mount(d)
    app._handle_event('{"id": 0, "event": "url", "payload": {"url": "myapp://details/9"}}')
    assert "id=9" in r.texts()
    import json
    monkeypatch.setenv("PYXPO_ENV", json.dumps({"initial_url": "myapp://details/3"}))
    app2, r2 = mount(d)
    assert "id=3" in r2.texts()


def test_claimed_url_is_not_opened_as_a_route(tmp_app):
    from pyxpo.apis.linking import Linking
    d = tmp_app({"_layout.py": LAYOUT, "index.py": INDEX, "details/[id].py": DETAILS})
    app, r = mount(d)
    Linking.claimed.append("myapp://details/")
    try:
        app._handle_event('{"id": 0, "event": "url", "payload": {"url": "myapp://details/9"}}')
        assert "id=9" not in r.texts()
    finally:
        Linking.claimed.remove("myapp://details/")
    app._handle_event('{"id": 0, "event": "url", "payload": {"url": "myapp://details/9"}}')
    assert "id=9" in r.texts()


def test_pressable_derives_accessibility_label_from_text():
    from pyxpo import Pressable, Text, View, create_app
    ch = LocalChannel()
    r = MockRenderer(ch)
    create_app(lambda: View(Pressable(Text("Save"), Text("now"), on_press=lambda: None),
                            Pressable(Text("x"), accessibility_label="Custom", on_press=lambda: None)), ch)
    labels = [n.props.get("accessibility_label") for n in r.find_all("View") if n.props.get("accessibility_label")]
    assert labels == ["Save now", "Custom"]


def _stack_state(r):
    ns = r.find_all("NavStack")[0]
    hidden = [c for c in ns.children if (c.props.get("style") or {}).get("display") == "none"]
    return ns, hidden


def test_stack_on_web_is_page_navigation(tmp_app, monkeypatch):
    import json
    d = tmp_app({"_layout.py": LAYOUT, "index.py": INDEX, "details/[id].py": DETAILS})
    app, r = mount(d)
    r.press(r.find_text("Open"))
    ns, _ = _stack_state(r)
    assert ns.props["animated"] is True and ns.props["gesture"] is True
    assert not any(p.props.get("href") for p in r.find_all("View"))
    from pyxpo.router import router
    router.push("/details/8")
    assert len(_stack_state(r)[1]) == 1  # native: only the top and the page under it stay laid out

    monkeypatch.setenv("PYXPO_ENV", json.dumps({"os": "web"}))
    app, r = mount(d)
    link = [v for v in r.find_all("View") if v.props.get("href")]
    assert [v.props["href"] for v in link] == ["/details/7"]
    r.press(r.find_text("Open"))
    ns, hidden = _stack_state(r)
    # No slide, no edge swipe; the page below stays mounted (its scroll is kept) and the page hides it.
    assert ns.props["animated"] is False and ns.props["gesture"] is False
    assert len(ns.children) == 2 and hidden == []
    assert "id=7" in r.texts()
    router.push("/details/8")
    ns, hidden = _stack_state(r)
    assert len(ns.children) == 3 and hidden == []
