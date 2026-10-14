from pathlib import Path

from pyxpo.config import pip_index_args


def test_empty(monkeypatch):
    monkeypatch.delenv("PYXPO_WHEEL_INDEX", raising=False)
    assert pip_index_args({}, Path("/p")) == []


def test_url_and_local(monkeypatch, tmp_path):
    monkeypatch.delenv("PYXPO_WHEEL_INDEX", raising=False)
    cfg = {"wheel_index": ["https://x.example/simple/", "wheels/dist", "/abs/w"]}
    assert pip_index_args(cfg, tmp_path) == [
        "--extra-index-url", "https://x.example/simple/",
        "--find-links", str((tmp_path / "wheels/dist").resolve()),
        "--find-links", "/abs/w",
    ]


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("PYXPO_WHEEL_INDEX", "https://a/simple, /w")
    got = pip_index_args({"wheel_index": ["https://ignored/"]}, Path("/p"))
    assert got == ["--extra-index-url", "https://a/simple", "--find-links", "/w"]
