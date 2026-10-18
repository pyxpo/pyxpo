# pyxpo-media-library

Save photos and videos to the phone's photo library from [pyxpo](https://github.com/pyxpo/pyxpo) apps, written in
Python, with the permission handling that goes with it. The API follows
[expo-media-library](https://docs.expo.dev/versions/latest/sdk/media-library/).

<p align="center">
  <img src="https://raw.githubusercontent.com/pyxpo/pyxpo/main/packages/media-library/docs/images/hero.png" width="820" alt="The media library module on Android and iOS: a sample photo, a Save to Photos button and the new asset details">
</p>

```python
from pyxpo_media_library import MediaLibrary

if (await MediaLibrary.request_permissions_async(write_only=True))["granted"]:
    asset = await MediaLibrary.create_asset_async(path)    # photo or video
```

## Features

- **Exact bytes:** the file goes into the library as it is, with no re-encoding.
- **Write-only permission:** ask only to add photos, which is a smaller request than reading the whole library.
  Android 10+ needs no permission to add.
- **Limited access:** a user who allowed only some photos gets `granted` with `accessPrivileges == "limited"`.
- **The new asset back:** `create_asset_async` returns its `id`, `uri`, `mediaType`, `width`, `height`, `duration` and
  `filename`.
- **Photos and videos.**
- **Works on the web and desktop:** the "library" is a folder on the desktop, and a download in the browser.
- **Typed:** ships `py.typed`. Every function has both spellings (`createAssetAsync`, `create_asset_async`).

## Contents

| If you are... | Start here |
| --- | --- |
| Adding a photo you made to the gallery | [Quick start](#quick-start) |
| Deciding what to ask for | [Permissions](#permissions) |
| Needing the new photo's id or size | [`create_asset_async`](#create_asset_async) |
| Only saving, not reading | [`save_to_library_async`](#save_to_library_async) |
| Targeting the web or a desktop window | [Web and desktop](#web-and-desktop) |
| Looking for exact signatures | [API reference](#api-reference) · [Errors](#errors) |
| Seeing it in a real app | [Recipe: save the result of an edit](#recipe-save-the-result-of-an-edit) |
| Stuck | [Testing](#testing) · [Troubleshooting](#troubleshooting) · [FAQ](#faq) |

## Platform support

| Target | What works |
| --- | --- |
| Android, API 24+ | Adding through `MediaStore`. No permission on Android 10+. `WRITE_EXTERNAL_STORAGE` is declared for Android 9 and older. Asset `uri` is a `content://` URI. |
| iOS 15+ | Adding through Photos. Asset `uri` is `ph://<id>`. |
| Web page (`pyxpo build web`) | A page cannot write to the library, so saving downloads the file to the browser's Downloads folder. |
| Desktop window | The library is a folder, `~/Pictures/pyxpo`, or `PYXPO_MEDIA_DIR` when set. Permissions are always granted. |

Requires Python 3.9+ and `pyxpo>=0.1.0a1`.

## Install

```sh
pip install pyxpo-media-library
```

```toml
[tool.pyxpo]
modules = ["media-library"]

# Optional: the text of the iOS prompts.
[tool.pyxpo.module_options.media-library]
addUsageDescription = "Save your drawings to your photo library."
usageDescription = "Pick photos from your library."
```

Rebuild the app after adding the module (`pyxpo run android` or `pyxpo run ios`).

| Option | iOS Info.plist key | Default text |
| --- | --- | --- |
| `addUsageDescription` | `NSPhotoLibraryAddUsageDescription` | "Save photos and videos to your photo library." |
| `usageDescription` | `NSPhotoLibraryUsageDescription` | "Access the photos and videos in your library." |

On Android the module declares `WRITE_EXTERNAL_STORAGE` (up to Android 9), `READ_EXTERNAL_STORAGE` (up to Android 12)
and `READ_MEDIA_IMAGES`, `READ_MEDIA_VIDEO` and `READ_MEDIA_VISUAL_USER_SELECTED` (Android 13+), as expo-media-library
does. Google Play restricts the `READ_MEDIA_*` permissions to apps that need broad photo access. If you only save, you
can remove them from your manifest.

## Quick start

```python
from pyxpo import Button, Image, Text, View, component, use_async, use_state
from pyxpo_media_library import MediaLibrary


@component
def SavePhoto(path: str):
    taps, set_taps = use_state(0)
    status, set_status = use_state("Not saved")

    async def save():
        if taps == 0:
            return
        perm = await MediaLibrary.request_permissions_async(write_only=True)
        if not perm["granted"]:
            set_status("Allow photo access in Settings to save")
            return
        asset = await MediaLibrary.create_asset_async(path)
        set_status("Saved %s (%sx%s)" % (asset["filename"], asset["width"], asset["height"]))

    use_async(save, [taps])
    return View(Image(source=path), Text(status), Button("Save to Photos", lambda: set_taps(taps + 1)))
```

> **Tip:** ask with `write_only=True` when you only add photos. The system prompt then asks only to add, which more
> people accept than full access.

<p align="center">
  <img src="https://raw.githubusercontent.com/pyxpo/pyxpo/main/packages/media-library/docs/images/library.png" width="720" alt="Saving a photo on Android and iOS and reading the permission and asset details">
</p>

## Permissions

```python
perm = await MediaLibrary.get_permissions_async(write_only=False)      # does not ask
perm = await MediaLibrary.request_permissions_async(write_only=True)   # asks if undetermined
```

The response is expo's `{"status", "granted", "canAskAgain", "expires"}` plus `accessPrivileges`.

| `accessPrivileges` | Meaning |
| --- | --- |
| `"all"` | The app can see and add everything. |
| `"limited"` | The user picked some photos only (iOS 14+, Android 14+). |
| `"none"` | No access. |

`write_only=True` covers only adding (`save_to_library_async`, `create_asset_async`). Adding needs no permission on
Android 10+, so the answer there is `granted` at once.

## `create_asset_async`

```python
asset = await MediaLibrary.create_asset_async("/path/to/photo.jpg")
```

Adds a local photo or video with its exact bytes and returns:

| Key | Meaning |
| --- | --- |
| `id` | The asset's id. |
| `uri` | `ph://<id>` on iOS, a `content://` URI on Android. |
| `mediaType` | `"photo"` or `"video"`. |
| `width`, `height` | Pixels. |
| `duration` | Seconds. `0` for photos. |
| `filename` | The file name in the library. |

The path must be a local file path or a `file://` URL. Needs write access only.

## `save_to_library_async`

```python
await MediaLibrary.save_to_library_async("/path/to/clip.mp4")
```

The same as `create_asset_async` when you do not need the asset back. Returns `None`.

## Errors

| Error | When | What to do |
| --- | --- | --- |
| `ValueError` | The path is empty, or a URL that is not `file://`. | Pass a local file path. Download remote files first. |
| `ModuleNotLinkedError` (from `pyxpo.module_api`) | Built without `"media-library"` in `modules`. | Add it and rebuild. |
| A native error | The file does not exist or cannot be read, or access was denied. | Check the path and ask for permission first. |
| `FileNotFoundError` (desktop and web) | The file is not there. | Check the path. |

## Config

See [Install](#install) for the two iOS prompt texts. A missing `NSPhotoLibraryAddUsageDescription` crashes an iOS app
that adds, so the module always writes a default.

## Web and desktop

| Environment | Behavior |
| --- | --- |
| Web page | `save_to_library_async` and `create_asset_async` download the file. The asset's `uri` points at the app's in-memory copy. Permissions are always `granted`. |
| Desktop window | The file is copied to `~/Pictures/pyxpo` (or `PYXPO_MEDIA_DIR`). A name clash gets a short suffix. Width and height are read with Pillow when it is installed, otherwise `0`. |

## Recipe: save the result of an edit

Edit a photo with `pyxpo-image-manipulator`, then save it and show where it went.

```python
from pyxpo import Button, Text, View, component, use_async, use_state
from pyxpo_image_manipulator import ImageManipulator
from pyxpo_media_library import MediaLibrary


@component
def Edit(path: str):
    taps, set_taps = use_state(0)
    note, set_note = use_state("")

    async def run():
        if taps == 0:
            return
        perm = await MediaLibrary.request_permissions_async(write_only=True)
        if not perm["granted"]:
            set_note("No permission. You can allow it in Settings.")
            return
        out = await ImageManipulator.manipulate_async(path, [{"rotate": 90}], {"compress": 0.8, "format": "jpeg"})
        asset = await MediaLibrary.create_asset_async(out["uri"])
        set_note("Saved as %s" % asset["filename"])

    use_async(run, [taps])
    return View(Text(note), Button("Rotate and save", lambda: set_taps(taps + 1)))
```

## Production checklist

- [ ] You ask with `write_only=True` when you only add.
- [ ] `addUsageDescription` says what you save, in the user's words.
- [ ] You handle `granted == False` with a way to Settings.
- [ ] A save failure shows a message, and the user can retry.
- [ ] You removed the `READ_MEDIA_*` permissions if you never read the library (Google Play review).
- [ ] You tested with "Limited" access on a real phone.

## Testing

Replace the native call and check what you sent:

```python
import asyncio

import pyxpo_media_library as M


def test_create_asset(monkeypatch):
    async def fake_call(*args, **kwargs):
        return {"id": "1", "uri": "ph://1", "mediaType": "photo", "width": 4, "height": 3, "duration": 0,
                "filename": "a.jpg"}

    monkeypatch.setattr(M, "call", fake_call)
    monkeypatch.setattr(M, "require_linked", lambda *a, **k: None)

    asset = asyncio.run(M.MediaLibrary.create_asset_async("/tmp/a.jpg"))
    assert asset["mediaType"] == "photo"
```

`MediaLibrary.create_asset_async("https://x/y.jpg")` raises `ValueError` before any native call.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| iOS crashes when saving | The Info.plist key is missing. Use the module (it adds a default) and rebuild. |
| No prompt appears | Permission was denied before. Send the user to Settings. |
| `ValueError: uri must be a local file path` | You passed an `http(s)` URL. Download it first. |
| The photo is not in the gallery on Android 9 | `WRITE_EXTERNAL_STORAGE` was denied. Ask with `request_permissions_async(write_only=True)`. |
| On the web nothing appears in Photos | A web page cannot reach the library. The file is in Downloads. |
| `accessPrivileges` is `"limited"` | The user chose some photos. Adding still works. |
| `ModuleNotLinkedError` | Add `"media-library"` to `modules` and rebuild. |

## FAQ

**Can I read the photos in the library?** Not yet. This module saves and manages permissions.

**Does saving re-encode?** No. The exact bytes are stored.

**Do I need a permission on Android?** Not to add on Android 10 and newer.

**Can I save to an album?** Not yet.

**Where is a saved photo on the desktop?** In `~/Pictures/pyxpo`.

## API reference

### `MediaLibrary`

| Function (camelCase name) | Returns |
| --- | --- |
| `get_permissions_async(write_only=False)` (`getPermissionsAsync`) | Permission response with `accessPrivileges`. |
| `request_permissions_async(write_only=False)` (`requestPermissionsAsync`) | The same, after asking. |
| `create_asset_async(uri)` (`createAssetAsync`) | The asset dict. |
| `save_to_library_async(local_uri)` (`saveToLibraryAsync`) | `None`. |

## License

MIT
