# pyxpo-media-library

Photo library permissions and saving photos and videos from pyxpo apps (expo-media-library shape).

This is an optional [pyxpo](https://github.com/pyxpo/pyxpo) native module. Apps that do not
list it carry none of its code, permissions or dependencies.

## Install

```bash
pip install pyxpo-media-library
```

Then link it into your app in `pyproject.toml`:

```toml
[tool.pyxpo]
modules = ["media-library"]
```

and rebuild (`pyxpo run ios`, `pyxpo build android`, ...). The build copies the module's Swift and Kotlin
sources into the native project and its Python package into the app.

## Use

```python
from pyxpo_media_library import MediaLibrary

if (await MediaLibrary.requestPermissionsAsync(writeOnly=True))["granted"]:
    asset = await MediaLibrary.createAssetAsync(path)   # photo or video; {"id", "uri", "mediaType", ...}
```

`getPermissionsAsync(writeOnly=False)` / `requestPermissionsAsync(writeOnly=False)` return expo's
`{"status", "granted", "canAskAgain", "expires", "accessPrivileges"}`; a user who allowed only some photos gets
`granted` with `accessPrivileges == "limited"`. Pass `writeOnly=True` when you only add to the library.

Permissions and Info.plist keys:

- iOS: `NSPhotoLibraryAddUsageDescription` (`addUsageDescription` option) and `NSPhotoLibraryUsageDescription`
  (`usageDescription` option), set with `[tool.pyxpo.module_options.media-library] addUsageDescription = "..."`.
- Android: adding needs no permission on Android 10+ (`WRITE_EXTERNAL_STORAGE` up to Android 9). Reading uses
  `READ_MEDIA_IMAGES` / `READ_MEDIA_VIDEO` / `READ_MEDIA_VISUAL_USER_SELECTED` on 13+ and `READ_EXTERNAL_STORAGE`
  before, declared like expo-media-library does. Google Play restricts the `READ_MEDIA_*` permissions to apps that
  need broad photo access.
- Asset `uri` is `ph://<id>` on iOS and a `content://` URI on Android; `duration` is in seconds (0 for photos).

## What is in the package

- `pyxpo_media_library/__init__.py`: the Python API.
- `pyxpo_media_library/pyxpo-module.json`: autolink metadata (bridge name, Swift and Kotlin classes, Android namespace and dependencies, Info.plist keys).
- `pyxpo_media_library/ios/`: Swift sources compiled into the iOS app.
- `pyxpo_media_library/android/src/main/`: Kotlin sources and the manifest merged into the Android app.
