from __future__ import annotations

import runpy
from pathlib import Path
from unittest import mock

from .test_core import mount


def test_rn_style_example_renders_and_adds():
    with mock.patch("pyxpo.run_app"):
        ns = runpy.run_path(str(Path(__file__).parent.parent / "examples" / "rn_style" / "main.py"))
    app, r = mount(ns["App"])
    texts = [n.props["text"] for n in r.find_all("Text")]
    assert texts == ["Todo", "Add", "Buy milk", "Write code"]
    inp = r.find_all("TextInput")[0]
    assert inp.props["placeholder"] == "New item"
