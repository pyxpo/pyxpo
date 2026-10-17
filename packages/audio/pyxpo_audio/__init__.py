"""Sound playback: the expo-audio player API.

    import pyxpo_audio as Audio

    @component
    def Song():
        player = Audio.use_audio_player("/path/song.wav", loop=True, volume=0.8)
        return Button("Play", player.play)      # player.pause(), player.seek_to(0), player.playing

    player = Audio.create_audio_player("https://example.com/beep.mp3")   # outside a component
    player.play()
    ...
    player.remove()                                                      # frees the native player

A source is a file path, a `file://` URI, an `http(s)://` URL or `{"uri": ...}`. The native player is made on the
first `play()` or `seek_to()`, so a player that never plays costs nothing. iOS and the Mac use AVAudioPlayer for
files (gapless loops) and AVPlayer for URLs, Android MediaPlayer, the web and the desktop window an HTML audio
element. Sound pauses while the app is in the background and plays on when it comes back. iOS plays even with
the silent switch on and mixes with other apps' sound.
"""
from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any, Dict, Optional, Union

from pyxpo.hooks import use_effect, use_memo
from pyxpo.module_api import call, require_linked

__version__ = "0.1.0a1"

Source = Union[str, Path, Dict[str, Any], None]

_ids = itertools.count(1)


def _uri(source: Source) -> Optional[str]:
    if isinstance(source, dict):
        source = source.get("uri")
    if source is None:
        return None
    if isinstance(source, Path):
        return str(source.resolve())
    if not isinstance(source, str) or not source:
        raise ValueError("source must be a path, a URI or {'uri': ...}, got %r" % (source,))
    return source


def _volume(v: Any) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1:
        raise ValueError("volume must be a number from 0 to 1, got %r" % (v,))
    return float(v)


class AudioPlayer:
    """Plays one sound. `playing` is what was last asked for (`play()` or `pause()`); a sound that does not loop
    stops by itself at its end while `playing` stays True, and the next `play()` starts it over."""

    def __init__(self, source: Source = None, *, loop: bool = False, volume: float = 1.0) -> None:
        self.uri = _uri(source)
        self.id = next(_ids)
        self.playing = False
        self._loop = bool(loop)
        self._volume = _volume(volume)
        self._made = False
        self._removed = False

    def _send(self, method: str, *args: Any) -> None:
        if self.uri is None or self._removed:
            return
        if not self._made:
            require_linked("Audio", "audio", package="pyxpo-audio")
            call("Audio", "create", self.id, self.uri, self._loop, self._volume)
            self._made = True
        call("Audio", method, self.id, *args)

    def play(self) -> None:
        """Plays from where it paused (from the start the first time, or after a sound without loop ended)."""
        if self._removed:
            return
        self.playing = True
        self._send("play")

    def pause(self) -> None:
        self.playing = False
        if self._made:
            self._send("pause")

    def seek_to(self, seconds: float) -> None:
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or seconds < 0:
            raise ValueError("seconds must be a number >= 0, got %r" % (seconds,))
        self._send("seek", float(seconds))

    @property
    def loop(self) -> bool:
        return self._loop

    @loop.setter
    def loop(self, value: bool) -> None:
        value = bool(value)
        if value != self._loop:
            self._loop = value
            if self._made:
                self._send("set", {"loop": value})

    @property
    def volume(self) -> float:
        return self._volume

    @volume.setter
    def volume(self, value: float) -> None:
        value = _volume(value)
        if value != self._volume:
            self._volume = value
            if self._made:
                self._send("set", {"volume": value})

    def remove(self) -> None:
        """Stops the sound and frees the native player. The player does nothing afterwards."""
        if self._made and not self._removed:
            call("Audio", "release", self.id)
        self._removed = True
        self.playing = False

    seekTo = seek_to


def create_audio_player(source: Source, *, loop: bool = False, volume: float = 1.0) -> AudioPlayer:
    """A player you own: call `remove()` when you are done with it."""
    return AudioPlayer(source, loop=loop, volume=volume)


def use_audio_player(source: Source, *, loop: bool = False, volume: float = 1.0) -> AudioPlayer:
    """A player for this component. A new source makes a new player; the old one and the last one when the
    component unmounts are removed. `loop` and `volume` follow the arguments on every render."""
    uri = _uri(source)
    player = use_memo(lambda: AudioPlayer(uri, loop=loop, volume=volume), [uri])
    use_effect(lambda: player.remove, [player])
    player.loop = loop
    player.volume = volume
    return player


createAudioPlayer = create_audio_player
useAudioPlayer = use_audio_player

__all__ = ["AudioPlayer", "create_audio_player", "use_audio_player", "createAudioPlayer", "useAudioPlayer"]
