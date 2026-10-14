import os

import pytest

from pyxpo.router.discovery import RouteError, discover, load_module, route_component
from pyxpo.router.matching import match, resolve

FILES = {
    "_layout.py": "", "index.py": "", "about.py": "", "+not-found.py": "",
    "user/[id].py": "", "user/new.py": "", "docs/[...rest].py": "", "_helper.py": "",
    "(tabs)/_layout.py": "", "(tabs)/home.py": "", "(tabs)/settings/index.py": "",
}


def names(m):
    return [s.name for s in m.chain]


def test_discovery_and_ranking(tmp_app):
    tree = discover(tmp_app(FILES))
    m = match(tree, "/user/new")
    assert names(m) == ["user/new"]
    m = match(tree, "/user/42?tab=a")
    assert names(m) == ["user/[id]"] and m.params == {"id": "42"} and m.query == {"tab": "a"}
    assert match(tree, "/docs/a/b/c").params == {"rest": ["a", "b", "c"]}
    assert names(match(tree, "/")) == ["index"]
    assert names(match(tree, "/home")) == ["(tabs)", "home"]
    assert names(match(tree, "/settings")) == ["(tabs)", "settings/index"]
    assert all("_helper" not in s.name for r in tree.routes for s in r.chain)


def test_not_found(tmp_app):
    tree = discover(tmp_app(FILES))
    m = match(tree, "/nope/x")
    assert not m.found and names(m) == ["+not-found"]
    os.remove(os.path.join(tmp_app({}), "+not-found.py"))
    assert match(discover(tmp_app({})), "/zzz").chain == []


def test_dict_and_relative_href(tmp_app):
    tree = discover(tmp_app(FILES))
    m = match(tree, {"pathname": "/user/[id]", "params": {"id": 7, "tab": "x"}})
    assert m.params == {"id": "7"} and m.query == {"tab": "x"} and m.pathname == "/user/7"
    assert resolve("../about", "/user/7")[0] == "/about"
    assert resolve("/(tabs)/home")[0] == "/home"


def test_load_module_by_path_and_default(tmp_app):
    root = tmp_app({"(g)/[id].py": "from pyxpo import component, Text\n@component\ndef Page():\n    return Text('x')\n"})
    tree = discover(root)
    scr = tree.routes[0].chain[-1]
    mod = load_module(scr.module_name, scr.file, root)
    assert scr.module_name == "app.(g).[id]"
    assert route_component(mod).fn.__name__ == "Page"
    assert load_module(scr.module_name, scr.file, root) is mod


def test_symlink_escape_rejected(tmp_app, tmp_path):
    root = tmp_app({"index.py": ""})
    outside = tmp_path.parent / "evil_route.py"
    outside.write_text("x = 1")
    os.symlink(str(outside), os.path.join(root, "evil.py"))
    tree = discover(root)
    assert [r.chain[-1].name for r in tree.routes] == ["index"]
    with pytest.raises(RouteError):
        load_module("app.evil", os.path.join(root, "evil.py"), root)
