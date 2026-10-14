from __future__ import annotations

from pyxpo import Text
from pyxpo import fonts
from pyxpo.style import normalize


def test_plain_text_and_transform():
    e = Text("hello world", style={"text_transform": "uppercase"})
    assert e.props["text"] == "HELLO WORLD" and "spans" not in e.props
    assert Text("hello big world", style={"text_transform": "capitalize"}).props["text"] == "Hello Big World"


def test_nested_spans_inherit():
    e = Text("a ", Text("b", style={"font_weight": "bold", "color": "red"}), " c",
             style={"color": "blue", "font_size": 20})
    sp = e.props["spans"]
    assert e.props["text"] == "a b c"
    assert [s["text"] for s in sp] == ["a ", "b", " c"]
    assert sp[0]["style"]["color"] == 0xFF0000FF and sp[0]["style"]["font_size"] == 20
    assert sp[1]["style"]["color"] == 0xFFFF0000 and sp[1]["style"]["font_weight"] == "bold"
    assert sp[1]["style"]["font_size"] == 20


def test_deep_nesting_transform():
    e = Text("x", Text("y", Text("z"), style={"text_transform": "uppercase"}))
    assert [s["text"] for s in e.props["spans"]] == ["x", "Y", "Z"]


def test_font_file_resolution(tmp_path, monkeypatch):
    d = tmp_path / "fonts"
    d.mkdir()
    (d / "Inter-Bold.ttf").write_bytes(b"x")
    monkeypatch.syspath_prepend(str(tmp_path))
    fonts._scanned.clear()
    st = normalize({"font_family": "Inter-Bold"})
    assert st["font_file"].endswith("Inter-Bold.ttf")
    assert "font_file" not in normalize({"font_family": "monospace"})


def test_text_shadow_color_normalized():
    assert normalize({"text_shadow_color": "#000"})["text_shadow_color"] == 0xFF000000
