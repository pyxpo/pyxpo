import base64
import hashlib
import importlib
import importlib.util
import os

import pytest

from pyxpo import LocalChannel, create_app
from pyxpo.dev.reloader import HotReloader
from pyxpo.renderers.mock import MockRenderer
from pyxpo.router import router
from pyxpo.router.discovery import discover
from pyxpo.router.root import RouterRoot

from .test_layouts import DETAILS, INDEX, LAYOUT

comp_mod = importlib.import_module("pyxpo.component")
ROUTER_ENTRY = importlib.util.find_spec("pyxpo.router.entry").origin  # not imported: the CLI runs it with runpy

PAGE = '''
from pyxpo import Text, component
@component
def About():
    return Text("about-page")
'''


def _upd(files=None, deleted=()):
    out = {}
    for rel, src in (files or {}).items():
        data = src.encode()
        out[rel] = {"sha1": hashlib.sha1(data).hexdigest(), "data": base64.b64encode(data).decode()}
    return {"files": out, "deleted": list(deleted)}


@pytest.fixture
def hot(tmp_app):
    comp_mod.enable_registry(True)
    d = tmp_app({"_layout.py": LAYOUT, "index.py": INDEX, "details/[id].py": DETAILS})
    ch = LocalChannel()
    r = MockRenderer(ch)
    app = create_app(RouterRoot, ch, tree=discover(d), root_dir=d)
    rl = HotReloader(app, os.path.dirname(d), ROUTER_ENTRY)
    yield app, r, rl, d
    comp_mod.enable_registry(False)


def test_router_entry_is_not_reexecuted(hot):
    app, r, rl, d = hot
    assert rl.entry is None


def test_edit_page_and_layout_keeps_route_and_stack(hot):
    app, r, rl, d = hot
    r.press(r.find_text("Open"))
    assert "id=7" in r.texts()
    assert rl.apply(_upd({"app/details/[id].py": DETAILS.replace('"id="', '"ID:"')}))
    assert "ID:7" in r.texts() and "id=7" not in r.texts()
    assert rl.apply(_upd({"app/_layout.py": LAYOUT.replace('"Details"', '"Detail view"')}))
    assert "Detail view" in r.texts() and "ID:7" in r.texts()
    assert router._s.pathname == "/details/7"
    assert router.canGoBack() is True
    router.back()
    assert "Open" in r.texts()


def test_added_route_is_navigable(hot):
    app, r, rl, d = hot
    assert rl.apply(_upd({"app/about.py": PAGE}))
    router.navigate("/about")
    assert "about-page" in r.texts()
    assert rl.apply(_upd({"app/about.py": PAGE.replace("about-page", "about-v2")}))
    assert "about-v2" in r.texts()


def test_deleting_current_route_shows_not_found(hot):
    app, r, rl, d = hot
    r.press(r.find_text("Open"))
    assert rl.apply(_upd(deleted=["app/details/[id].py"]))
    assert not os.path.exists(os.path.join(d, "details", "[id].py"))
    assert "Unmatched Route" in r.texts()
    router.back()
    assert "Open" in r.texts()


def test_syntax_error_changes_nothing(hot):
    app, r, rl, d = hot
    r.press(r.find_text("Open"))
    before = router._s.state
    assert not rl.apply(_upd({"app/details/[id].py": "def D(:\n", "app/about.py": PAGE}))
    assert any("syntax error" in t for t in r.texts())
    assert not os.path.exists(os.path.join(d, "about.py"))
    assert router._s.state is before and "id=7" in r.texts()
    assert rl.apply(_upd({"app/details/[id].py": DETAILS.replace('"id="', '"fixed="')}))
    assert "fixed=7" in r.texts() and not any("syntax error" in t for t in r.texts())
