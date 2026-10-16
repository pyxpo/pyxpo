from __future__ import annotations

from pathlib import Path

import pytest

from pyxpo.router.discovery import discover
from pyxpo.router.root import RouterRoot

from .test_core import mount

EXAMPLES = Path(__file__).parent.parent / "examples"


@pytest.fixture(autouse=True)
def _clean_modules():
    import sys

    def clean():
        for k in [k for k in sys.modules if k == "app" or k.startswith("app.")]:
            del sys.modules[k]
    clean()  # other tests (test_cli) may leave their own `app` package imported
    yield
    clean()


def test_rn_style_example_renders_and_adds():
    d = str(EXAMPLES / "rn_style" / "app")
    app, r = mount(RouterRoot, tree=discover(d), root_dir=d)
    texts = [n.props["text"] for n in r.find_all("Text")]
    assert texts == ["Todo", "Add", "Buy milk", "Write code"]
    assert r.find_all("TextInput")[0].props["placeholder"] == "New item"


def test_counter_example_navigates():
    from pyxpo.router import router
    d = str(EXAMPLES / "counter" / "app")
    app, r = mount(RouterRoot, tree=discover(d), root_dir=d)
    r.press(r.find_text("Add"))
    r.press(r.find_text("Open details"))
    assert "Count was 1" in r.texts()
    router.back()
    assert "Count was 1" not in r.texts()
