# pyxpo-video

A video player for [pyxpo](https://github.com/pyxpo/pyxpo) apps, written in Python. `VideoView` plays a local
file or an http(s) URL inside your layout, with the platform's own playback controls. It uses AVPlayer on iOS and
the Mac, `VideoView` on Android, and a `<video>` element on the web page and the desktop window.

<p align="center">
  <img src="https://raw.githubusercontent.com/pyxpo/pyxpo/main/packages/video/docs/images/hero.png" width="820" alt="The same pyxpo-video demo playing an 8 second clip on the iOS simulator and the Android emulator">
</p>

```python
import pyxpo_video as Video

Video.VideoView(source="/path/clip.mp4", style={"width": 270, "height": 480})   # plays at once
```

## Features

- **One component:** `VideoView` sits in your layout like any other view and takes its size from `style`.
- **Native players:**
  - iOS and Mac Catalyst: AVPlayer in an `AVPlayerViewController`, with the system controls.
  - Android: `android.widget.VideoView` with a `MediaController`.
  - Web page and desktop window: an HTML `<video>` element.
- **Local files and URLs:** a file path, a `file://` URI or an `http(s)` URL.
- **Simple props:** `playing`, `loop`, `muted`, `controls` and `resize_mode` (`"contain"`, `"cover"`, `"stretch"`).
- **Events:** `on_load` with the duration and the video size, `on_error` with a message, `on_end` at the end.
- **Control from code:** `ref.current.play()`, `.pause()` and `.seek(seconds)`.
- **Typed:** ships `py.typed`.

## Contents

| If you are... | Start here |
| --- | --- |
| New to the package | [Quick start](#quick-start) → [Sources](#sources) → [Props](#props) |
| Controlling playback from buttons | [Play, pause and seek](#play-pause-and-seek) |
| Filling a frame or a card | [Resize modes](#resize-modes) |
| Reacting to the video | [Events and errors](#events-and-errors) |
| Seeing it in a real app | [Recipe: a preview of a file your app just made](#recipe-a-preview-of-a-file-your-app-just-made) |
| Looking for exact signatures | [API reference](#api-reference) |
| Stuck | [Testing](#testing) · [Troubleshooting](#troubleshooting) · [FAQ](#faq) |

## Platform support

| Target | Player | Notes |
| --- | --- | --- |
| Android, API 24+ | `android.widget.VideoView` + `MediaController` | `resize_mode` is always `"contain"`. The controls show on a tap. |
| iOS 15+ | AVPlayer (`AVPlayerViewController`) | All props. The controls hide while playing and come back on a tap. |
| Mac Catalyst | AVPlayer, same code as iOS | All props. |
| Web page (`pyxpo build web`) | `<video>` | Local files come from the app's in-browser file system. |
| Desktop window (`pyxpo run desktop`) | `<video>` | Local files come from the dev server with byte ranges, so seeking works. |

The formats are the platform's own. H.264 video with AAC audio in an `.mp4` file plays everywhere.

Requires Python 3.9+ and `pyxpo>=0.1.0a3`.

## Install

```sh
pip install pyxpo-video
```

Add the module to your app's `pyproject.toml`:

```toml
[tool.pyxpo]
modules = ["video"]
```

The module has native code, so rebuild the app after adding it (`pyxpo run android` or `pyxpo run ios`). It has no
config plugin and needs no permissions. Android apps already have the `INTERNET` permission for URLs.

## Quick start

A player with its own Play, Pause and Restart buttons, and a status line:

```python
import os

from pyxpo import Button, Text, View, component, use_ref, use_state
import pyxpo_video as Video

CLIP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "clip.mp4")


@component
def Player():
    player = use_ref(None)
    info, set_info = use_state(None)
    problem, set_problem = use_state("")

    status = problem or ("%.1f s, %d x %d" % (info["duration"], info["width"], info["height"]) if info else "loading")
    return View(
        View(
            Video.VideoView(ref=player, source=CLIP, playing=True, muted=True,
                            on_load=set_info, on_error=lambda e: set_problem(e["message"]),
                            style={"flex": 1}),
            style={"width": 260, "height": 400, "borderRadius": 16, "overflow": "hidden",
                   "backgroundColor": "#000"},
        ),
        Text(status),
        View(
            Button(title="Play", on_press=lambda: player.current.play()),
            Button(title="Pause", on_press=lambda: player.current.pause()),
            Button(title="Restart", on_press=lambda: player.current.seek(0)),
            style={"flexDirection": "row", "gap": 8},
        ),
        style={"flex": 1, "alignItems": "center", "justifyContent": "center"},
    )


default = Player
```

`pyxpo build` copies the app's `assets/` folder into the app, so `assets/clip.mp4` sits next to `app/` on every
platform. The screenshots above come from this app with one more button that switches `resize_mode`.

## Sources

`source` takes one of these:

| Value | Example | Notes |
| --- | --- | --- |
| A file path | `"/data/user/0/com.acme.app/files/reel.mp4"` | Absolute paths are best. Build them from `__file__` or a folder API. |
| A `file://` URI | `"file:///Users/me/reel%20one.mp4"` | Turned into a path; `%20` and other escapes are decoded. Only local hosts (`file:///` or `file://localhost/`). |
| An `http://` or `https://` URL | `"https://example.com/clip.mp4"` | Streams. iOS blocks plain `http://` to the internet (App Transport Security), so use `https://`. |
| `None` | | Shows an empty black box and stops playback. |

Anything else (an empty string, `rtsp://`, a `file://` URI with another host, a number) raises `ValueError` when the
component renders.

When `source` changes, the player loads the new video and fires `on_load` again.

> **Tip:** When your app writes a new video to the same path, the player keeps the old one. Change the component's
> `key` (for example to the file's modification time) to make a new player that loads the new file. The
> [recipe](#recipe-a-preview-of-a-file-your-app-just-made) shows this.

## Props

| Prop | Type | Default | What it does |
| --- | --- | --- | --- |
| `source` | `str` or `None` | `None` | The video. See [Sources](#sources). |
| `playing` | `bool` | `True` | Plays when True, pauses when False. It acts when it changes; the user can still play and pause with the controls. |
| `loop` | `bool` | `False` | Starts again at the end. `on_end` does not fire while looping. |
| `muted` | `bool` | `False` | No sound. Use it for videos that start by themselves. |
| `controls` | `bool` | `True` | Shows the platform's playback controls. |
| `resize_mode` | `str` | `"contain"` | `"contain"`, `"cover"` or `"stretch"`. See [Resize modes](#resize-modes). |
| `on_load` | `callable` | `None` | `on_load(info)` when the video is ready. |
| `on_error` | `callable` | `None` | `on_error(error)` when the video cannot play. |
| `on_end` | `callable` | `None` | `on_end(None)` when the video reaches its end (not with `loop=True`). |
| `style` | style | `None` | Size and position. Give the player a size: a `width` and `height`, `flex: 1`, or `aspectRatio`. |
| `ref` | ref | | `ref.current` is a [`VideoViewHandle`](#play-pause-and-seek). |

Other props (`key`, `test_id`, ...) pass through like on any view.

## Play, pause and seek

Pass a ref and call the handle's methods from a button or an effect:

```python
from pyxpo import Button, View, component, use_ref
import pyxpo_video as Video


@component
def Clip(path):
    player = use_ref(None)
    return View(
        Video.VideoView(ref=player, source=path, playing=False, style={"width": "100%", "aspectRatio": 9 / 16}),
        Button(title="Jump to 0:05", on_press=lambda: player.current.seek(5)),
    )
```

| Method | What it does |
| --- | --- |
| `play()` | Starts or resumes playback. |
| `pause()` | Pauses playback. |
| `seek(seconds)` | Jumps to `seconds` from the start. `seconds` must be a number `>= 0`; anything else raises `ValueError`. |

The methods change the player, not the `playing` prop. When `playing` changes later, the prop wins again. To keep
both in step, hold `playing` in state and change the state instead of calling `play()` and `pause()`.

The methods raise `RuntimeError("the VideoView is not mounted")` before the view is on screen, and a link error that
names `pyxpo-video` when the app was built without `modules = ["video"]`.

## Resize modes

<p align="center">
  <img src="https://raw.githubusercontent.com/pyxpo/pyxpo/main/packages/video/docs/images/fit.png" width="820" alt="A portrait clip in a 260 x 400 box on iOS: contain shows black bars at the sides, cover fills the box">
</p>

| `resize_mode` | Result | iOS / Mac | Android | Web / desktop |
| --- | --- | --- | --- | --- |
| `"contain"` | The whole video, with black bars where the shapes differ. | `.resizeAspect` | yes | `object-fit: contain` |
| `"cover"` | Fills the box and crops the edges. | `.resizeAspectFill` | shows `"contain"` | `object-fit: cover` |
| `"stretch"` | Fills the box and distorts the picture. | `.resize` | shows `"contain"` | `object-fit: fill` |

For a frame that always fits, give the box the video's shape: `style={"width": "100%", "aspectRatio": 9 / 16}` for
a vertical reel. Then all three modes look the same on every platform.

## Events and errors

| Event | Argument | When |
| --- | --- | --- |
| `on_load` | `{"duration": 8.0, "width": 720.0, "height": 1280.0}` | The video is ready. Seconds and pixels. `duration` is `0` for a live stream. |
| `on_error` | `{"message": "..."}` | The file or URL cannot play. |
| `on_end` | `None` | Playback reached the end and `loop` is False. |

The `message` comes from the platform, so its text differs:

| Platform | Typical message | What to do |
| --- | --- | --- |
| iOS / Mac | AVFoundation's `localizedDescription`, for example "The file couldn't be opened." | Check that the path exists and the format is H.264 or HEVC in `.mp4` or `.mov`. |
| Android | `cannot play the video (error 1, -2147483648)` | `MediaPlayer` error codes. `1, -1004` is an I/O error (missing file, network); `1, -2147483648` usually means an unsupported format. |
| Web / desktop | The browser's `MediaError.message`, or `cannot play the video` | Check the browser console. |

A bad prop value (`resize_mode="fill"`, `source=""`) is a `ValueError` from Python, not an `on_error` call.

## Web and desktop

`pyxpo run desktop` and the web build render `VideoView` as a `<video>` element with `playsinline`:

- `http(s)` URLs load directly, so they follow the browser's CORS and mixed-content rules.
- In the desktop window, local files come from the dev server at `/file`, which answers byte-range requests. That
  lets the browser seek and lets WebKit play the file at all.
- In the web build, local files come from the in-browser file system as `blob:` URLs.
- Browsers block sound in videos that start by themselves. Set `muted=True` when `playing=True` at load, or start
  playback from a button press.

## Recipe: a preview of a file your app just made

An app that renders a video (say, a reel) shows a spinner while it works and the finished file after. A changing
`key` reloads the player each time the file is written again:

```python
import os

from pyxpo import ActivityIndicator, Text, View, component
import pyxpo_video as Video


@component
def Preview(path, rendering):
    frame = {"width": 270, "height": 480, "borderRadius": 24, "overflow": "hidden", "backgroundColor": "#000"}
    if rendering:
        return View(ActivityIndicator(), Text("Rendering..."), style=dict(frame, justifyContent="center",
                                                                            alignItems="center"))
    if not os.path.exists(path):
        return View(Text("No video yet", style={"color": "#fff"}), style=dict(frame, justifyContent="center",
                                                                              alignItems="center"))
    mtime = int(os.path.getmtime(path))
    return Video.VideoView(source=path, playing=False, controls=True, style=frame, key="player-%d" % mtime)
```

`playing=False` waits for the user to press play in the controls.

## Production checklist

- Ship H.264 + AAC in `.mp4` for the widest support. HEVC is smaller but older Android phones cannot play it.
- Use `https://` URLs. iOS blocks plain `http://`, and Android release builds block it unless you set
  `uses_cleartext_traffic = true` under `[tool.pyxpo.android]`.
- Give every `VideoView` a size in `style`. A player with no size has zero height.
- Set `muted=True` for videos that play by themselves.
- Handle `on_error` and show a message. Files go missing and networks fail.
- Keep large videos out of `assets/`: they go into the app bundle. Download them to a folder at run time instead.
- Test on a real phone. The emulator and the simulator decode in software and can stutter where a phone does not.

## Testing

`VideoView` renders a `PxVideoView` node, so the mock renderer shows its props and can fire its events:

```python
from pyxpo import LocalChannel, component, create_app
from pyxpo.renderers.mock import MockRenderer
import pyxpo_video as Video


def test_shows_the_duration():
    got = []

    @component
    def Root():
        return Video.VideoView(source="/tmp/a.mp4", playing=False, on_load=got.append)

    ch = LocalChannel()
    r = MockRenderer(ch)
    create_app(Root, ch)
    (node,) = r.find_all("PxVideoView")
    assert node.props["source"] == "/tmp/a.mp4" and node.props["playing"] is False
    r.emit("load", node, {"value": {"duration": 8.0, "width": 720.0, "height": 1280.0}})
    assert got[0]["duration"] == 8.0
```

`play()`, `pause()` and `seek()` call the native module. In a unit test, answer them with
`pyxpo.module_testing.FakeBridge`:

```python
from pyxpo.module_testing import FakeBridge

with FakeBridge("android") as fb:
    for m in ("play", "pause", "seek"):
        fb.on("Video", m, lambda *a: None)
    ref.current.seek(2)                      # ref from a mounted VideoView
    assert fb.calls[-1][:3] == ("Video", "seek", (tag, 2.0))
```

## Troubleshooting

| Problem | Cause and fix |
| --- | --- |
| The player is not there at all | It has no size. Give it `width`/`height`, `flex: 1` or `aspectRatio`. |
| A black box and no `on_load` | Wrong path. Print `os.path.exists(path)`. For bundled files, build the path from `__file__`. |
| A black box on Android with `playing=False` | Android's `VideoView` draws nothing until playback starts. Press play in the controls or call `play()`. |
| `on_error` on iOS for an `http://` URL | App Transport Security. Use `https://`. |
| No sound | `muted=True`, the phone's silent switch on iOS, or the browser's autoplay rule on the web. |
| `cover` looks like `contain` on Android | Android supports `"contain"` only. Give the box the video's aspect ratio instead. |
| The old video still plays after the file changed | The source string is the same. Change `key` (see the [recipe](#recipe-a-preview-of-a-file-your-app-just-made)). |
| `RuntimeError: the VideoView is not mounted` | `play()` ran before the view was on screen, or after it was removed. Call it from `on_load` or a button. |
| An error that names `pyxpo-video` | The app was built without the module. Add `modules = ["video"]` and rebuild. |
| The controls are not visible on iOS | They hide while playing. Tap the video. |

## FAQ

**Can it play YouTube or Instagram links?**
No. Those are web pages, not video files. `source` needs a direct link to a media file (`.mp4`, `.mov`, `.m3u8`).

**Does it play HLS (`.m3u8`)?**
On iOS, the Mac and Android, yes: AVPlayer and `MediaPlayer` play HLS. On the web, only Safari plays it natively.

**Can it play in the background or picture-in-picture?**
Not in this version. The video pauses with the app.

**Does it cache downloaded videos?**
No. For offline playback, download the file first (for example with `pyxpo-file-system`) and pass the local path.

## API reference

### `VideoView(...)`

```text
VideoView(source=None, playing=True, loop=False, muted=False, controls=True, resize_mode="contain",
          on_load=None, on_error=None, on_end=None, style=None, **props)
```

A component. See [Props](#props). Raises `ValueError` for a bad `source` or `resize_mode`.

### `VideoViewHandle`

`ref.current` of a mounted `VideoView`.

| Member | Returns | Raises |
| --- | --- | --- |
| `play()` | `None` | `RuntimeError` when not mounted; a link error without the module |
| `pause()` | `None` | same |
| `seek(seconds: float)` | `None` | `ValueError` for a negative, infinite or non-number value; same as above |

### Constants

| Name | Value |
| --- | --- |
| `RESIZE_MODES` | `("contain", "cover", "stretch")` |
| `__version__` | The package version |

## License

MIT. See [LICENSE](LICENSE).
