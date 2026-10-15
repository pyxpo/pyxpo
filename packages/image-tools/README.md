# pyxpo-image-tools

On-device image processing for pyxpo apps: info, crop, resize, convert, strip metadata, compress under a size.

This is an optional [pyxpo](https://github.com/ivishalchaubey/pyxpo) native module. Apps that do not
list it carry none of its code, permissions or dependencies.

## Install

```bash
pip install pyxpo-image-tools
```

Then link it into your app in `pyproject.toml`:

```toml
[tool.pyxpo]
modules = ["image-tools"]
```

and rebuild (`pyxpo run ios`, `pyxpo build android`, ...). The build copies the module's Swift and Kotlin
sources into the native project and its Python package into the app.

## Use

```python
from pyxpo_image_tools import ImageTools

info = await ImageTools.getInfo(path)
small = await ImageTools.compressToSize(path, maxBytes=200_000)
```

Permissions and Info.plist keys: none.

## What is in the package

- `pyxpo_image_tools/__init__.py`: the Python API.
- `pyxpo_image_tools/pyxpo-module.json`: autolink metadata (bridge name, Swift and Kotlin classes, Android namespace and dependencies, Info.plist keys).
- `pyxpo_image_tools/ios/`: Swift sources compiled into the iOS app.
- `pyxpo_image_tools/android/src/main/`: Kotlin sources and the manifest merged into the Android app.
