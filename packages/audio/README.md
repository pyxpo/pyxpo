# pyxpo-audio

Sound playback for pyxpo apps: play, pause, loop, seek and volume for local files and URLs. The API follows
the player part of expo-audio.

This is an optional [pyxpo](https://github.com/pyxpo/pyxpo) native module. Apps that do not
list it carry none of its code, permissions or dependencies.

## Install

```bash
pip install pyxpo-audio
```

Then link it into your app in `pyproject.toml`:

```toml
[tool.pyxpo]
modules = ["audio"]
```

and rebuild (`pyxpo run ios`, `pyxpo build android`, ...).

## Use

```python
import pyxpo_audio as Audio

@component
def Song():
    player = Audio.use_audio_player("/path/song.wav", loop=True, volume=0.8)   # or Audio.useAudioPlayer
    return Button("Pause" if player.playing else "Play",
                  lambda: player.pause() if player.playing else player.play())
```

- `use_audio_player(source, loop=False, volume=1.0)`: a player for this component. A new source makes a new
  player. The old player, and the last one when the component unmounts, stop and are freed.
- `create_audio_player(source, ...)`: a player you own. Call `remove()` when you are done.
- `player.play()`, `player.pause()`, `player.seek_to(seconds)`, `player.remove()`.
- `player.loop` and `player.volume` (0 to 1) can be changed at any time. `player.playing` is what was last
  asked for.

A source is a file path, a `file://` URI, an `http(s)://` URL or `{"uri": ...}`. `None` plays nothing.

## Platforms

- iOS and the Mac: AVAudioPlayer for files (gapless loops), AVPlayer for URLs. Sound plays with the silent
  switch on and mixes with other apps' sound.
- Android: MediaPlayer. A play asked for while the file prepares starts when it is ready.
- Web and the desktop window: an HTML audio element. Browsers play sound only after the first tap on the page.

Sound pauses while the app is in the background (or the tab is hidden) and plays on when it comes back.
