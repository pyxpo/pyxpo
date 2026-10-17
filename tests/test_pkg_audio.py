"""pyxpo-audio: lazy native player, play/pause/seek/set/release calls, value checks and not linked."""
from pathlib import Path

import pytest

from pyxpo.module_testing import FakeBridge

import pyxpo_audio as Audio

METHODS = ("create", "play", "pause", "seek", "set", "release")



def listen(fb):
    for m in METHODS:
        fb.on("Audio", m, lambda *a: None)


def test_lazy_create_and_calls():
    with FakeBridge("ios") as fb:
        listen(fb)
        p = Audio.create_audio_player("/music/a.wav", loop=True, volume=0.5)
        p.pause()                      # nothing made yet: no call
        p.volume = 0.7                 # kept for create
        assert fb.calls == []
        p.play()
        assert p.playing
        p.seek_to(2)
        p.pause()
        p.loop = False
        p.loop = False                 # same value: no call
        p.volume = 0.2
        p.remove()
        p.play()                       # removed: no call
        i = p.id
        assert fb.calls == [
            ("Audio", "create", (i, "/music/a.wav", True, 0.7)), ("Audio", "play", (i,)),
            ("Audio", "seek", (i, 2.0)), ("Audio", "pause", (i,)), ("Audio", "set", (i, {"loop": False})),
            ("Audio", "set", (i, {"volume": 0.2})), ("Audio", "release", (i,)),
        ]
        assert not p.playing


def test_sources():
    assert Audio.AudioPlayer({"uri": "https://x/y.mp3"}).uri == "https://x/y.mp3"
    assert Audio.AudioPlayer(Path("a.wav")).uri == str(Path("a.wav").resolve())
    with FakeBridge("android") as fb:
        listen(fb)
        p = Audio.AudioPlayer(None)
        p.play()
        p.seek_to(1)
        p.remove()
        assert fb.calls == []          # no source: nothing to play
    for bad in ("", 3, {"uri": 4}):
        with pytest.raises(ValueError, match="source"):
            Audio.AudioPlayer(bad)


def test_bad_values():
    for v in (-0.1, 1.5, "loud", True, None):
        with pytest.raises(ValueError, match="volume"):
            Audio.AudioPlayer("a.wav", volume=v)
    p = Audio.AudioPlayer("a.wav")
    for s in (-1, "1", True):
        with pytest.raises(ValueError, match="seconds"):
            p.seek_to(s)
    with pytest.raises(ValueError, match="volume"):
        p.volume = 2


def test_camel_aliases():
    assert Audio.createAudioPlayer is Audio.create_audio_player
    assert Audio.useAudioPlayer is Audio.use_audio_player
    assert Audio.AudioPlayer.seekTo is Audio.AudioPlayer.seek_to


def test_not_linked():
    from pyxpo.module_api import ModuleNotLinkedError
    with FakeBridge("android"):
        with pytest.raises(ModuleNotLinkedError):
            Audio.create_audio_player("a.wav").play()


def test_use_audio_player_follows_source_and_unmount():
    from pyxpo import LocalChannel, View, component, create_app, use_state
    from pyxpo.renderers.mock import MockRenderer
    seen, setters = [], {}

    @component
    def Song():
        props, set_props = use_state({"src": "a.wav", "volume": 1.0})
        setters["props"] = set_props
        p = Audio.use_audio_player(props["src"], loop=True, volume=props["volume"])
        seen.append(p)
        return View()

    @component
    def Root():
        on, set_on = use_state(True)
        setters["on"] = set_on
        return Song() if on else View()

    ch = LocalChannel()
    MockRenderer(ch)
    app = create_app(Root, ch)
    with FakeBridge("ios") as fb:   # after create_app, which sets the bridge's app
        listen(fb)
        first = seen[-1]
        first.play()
        setters["props"]({"src": "a.wav", "volume": 0.5})
        app.flush()
        assert seen[-1] is first and first.volume == 0.5
        setters["props"]({"src": "b.wav", "volume": 0.5})
        app.flush()
        second = seen[-1]
        assert second is not first and second.loop
        second.play()
        setters["on"](False)
        app.flush()
        assert [c for c in fb.calls if c[1] in ("create", "release")] == [
            ("Audio", "create", (first.id, "a.wav", True, 1.0)), ("Audio", "release", (first.id,)),
            ("Audio", "create", (second.id, "b.wav", True, 0.5)), ("Audio", "release", (second.id,)),
        ]
