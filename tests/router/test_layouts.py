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
