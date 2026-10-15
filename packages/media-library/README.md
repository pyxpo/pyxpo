# pyxpo-media-library

Save files to the device photo library from pyxpo apps (expo-media-library shape).

This is an optional [pyxpo](https://github.com/ivishalchaubey/pyxpo) native module. Apps that do not
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

if (await MediaLibrary.requestPermissionsAsync())["granted"]:
    await MediaLibrary.saveToLibraryAsync(path)
```

Permissions and Info.plist keys: iOS `NSPhotoLibraryAddUsageDescription` (set it with `[tool.pyxpo.module_options.media-library] addUsageDescription = "..."`).

## What is in the package

- `pyxpo_media_library/__init__.py`: the Python API.
- `pyxpo_media_library/pyxpo-module.json`: autolink metadata (bridge name, Swift and Kotlin classes, Android namespace and dependencies, Info.plist keys).
- `pyxpo_media_library/ios/`: Swift sources compiled into the iOS app.
- `pyxpo_media_library/android/src/main/`: Kotlin sources and the manifest merged into the Android app.
