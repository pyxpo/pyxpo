from __future__ import annotations

import base64
import importlib
import hashlib
import os
import sys
import textwrap

import pytest

from pyxpo import LocalChannel, create_app
comp_mod = importlib.import_module("pyxpo.component")
from pyxpo.dev.reloader import HotReloader
from pyxpo.renderers.mock import MockRenderer

MAIN = """
from pyxpo import Button, Text, View, component, use_state
from app.ui import label

@component
def Root():
    n, set_n = use_state(0)
    return View(Text(label(), n), Button(title="Add", on_press=lambda: set_n(lambda c: c + 1)))
"""
UI = "def label():\n    return 'Count: '\n"


def _upd(files=None, deleted=()):
    out = {}
    for rel, src in (files or {}).items():
        data = textwrap.dedent(src).encode() if isinstance(src, str) else src
        out[rel] = {"sha1": hashlib.sha1(data).hexdigest(), "data": base64.b64encode(data).decode()}
    return {"files": out, "deleted": list(deleted)}


@pytest.fixture
def proj(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "main.py").write_text(textwrap.dedent(MAIN))
    (tmp_path / "app" / "ui.py").write_text(UI)
    base = os.path.realpath(tmp_path)
    for k in [k for k in sys.modules if k == "app" or k.startswith("app.")]:
        del sys.modules[k]
    sys.path.insert(0, base)
    comp_mod.enable_registry(True)
    main = importlib.import_module("app.main")
    ch = LocalChannel()
    r = MockRenderer(ch)
    app = create_app(main.Root, ch)
    yield app, r, HotReloader(app, base, os.path.join(base, "app", "main.py")), base
    comp_mod.enable_registry(False)
    comp_mod._registry.clear()
    sys.path.remove(base)
    for k in [k for k in sys.modules if k == "app" or k.startswith("app.")]:
        del sys.modules[k]


def test_edit_dependency_keeps_state(proj):
    app, r, rl, base = proj
    r.press(r.find_text("Add"))
    assert r.texts() == ["Count: 1"]
    assert rl.apply(_upd({"app/ui.py": "def label():\n    return 'N='\n"}))
    assert r.texts() == ["N=1"]
    r.press(r.find_text("Add"))
    assert r.texts() == ["N=2"]


def test_edit_entry_keeps_state(proj):
    app, r, rl, base = proj
    r.press(r.find_text("Add"))
    src = open(os.path.join(base, "app", "main.py")).read().replace('"Add"', '"Plus"')
    assert rl.apply(_upd({"app/main.py": src.encode()}))
    assert "Plus" in r.texts() or r.find_text("Plus") is not None
    assert r.texts() == ["Count: 1"]


def test_syntax_error_changes_nothing(proj):
    app, r, rl, base = proj
    assert not rl.apply(_upd({"app/ui.py": "def label(:\n"}))
    assert open(os.path.join(base, "app", "ui.py")).read() == UI
    assert any("syntax error" in t for t in r.texts())
    assert rl.apply(_upd({"app/ui.py": "def label():\n    return 'ok '\n"}))
    assert r.texts() == ["ok 0"]


def test_import_error_rolls_back(proj):
    app, r, rl, base = proj
    assert not rl.apply(_upd({"app/ui.py": "raise RuntimeError('boom')\n"}))
    assert sys.modules["app.ui"].label() == "Count: "
    assert any("boom" in t for t in r.texts())
    assert rl.apply(_upd({"app/ui.py": "def label():\n    return 'fixed '\n"}))
    assert r.texts() == ["fixed 0"]


def test_render_error_remount_fails_then_recovers(proj):
    app, r, rl, base = proj
    assert not rl.apply(_upd({"app/ui.py": "def label():\n    raise ValueError('bad')\n"}))
    assert app.broken
    assert rl.apply(_upd({"app/ui.py": "def label():\n    return 'back '\n"}))
    assert not app.broken
    assert r.texts() == ["back 0"]


def test_path_traversal_rejected(proj):
    app, r, rl, base = proj
    assert not rl.apply(_upd({"../evil.py": "x=1\n"}))
    assert not os.path.exists(os.path.join(os.path.dirname(base), "evil.py"))


def test_reload_all_resets_state_and_says_so(proj, capsys):
    app, r, rl, base = proj
    r.press(r.find_text("Add"))
    assert r.texts() == ["Count: 1"]
    assert rl.reload_all()
    assert r.texts() == ["Count: 0"]
    assert "[pyxpo dev] reloaded the app" in capsys.readouterr().err
