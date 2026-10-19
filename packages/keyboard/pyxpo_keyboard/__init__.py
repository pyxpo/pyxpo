"""A system keyboard for pyxpo apps.

    import pyxpo_keyboard as Keyboard

    s = await Keyboard.status_async()          # {"supported", "enabled", "selected", "id"}
    if not s["enabled"]:
        await Keyboard.open_settings_async()   # Settings > Keyboards: the user turns it on
    elif not s["selected"]:
        await Keyboard.show_picker_async()     # the system's "choose keyboard" dialog
    await Keyboard.set_options_async(number_row=True, haptics=False)

On Android the module adds an input method (InputMethodService) named after the app. Its keys are native:
typing never waits for Python. Password, PIN and incognito fields are private (`FieldInfo.sensitive`).
iOS keyboards are app extensions, which this version does not add: `status_async` reports
`supported: False`. On the web and the desktop every call returns the defaults and does nothing.
"""
from __future__ import annotations

from typing import Any, Dict

from pyxpo.module_api import NotSupportedError, call, platform, require_linked

__version__ = "0.1.0a1"

#: Options the keyboard reads on every field, with their defaults.
OPTIONS: Dict[str, bool] = {
    "number_row": False,           # a row of digits above the letters (else long-press the top row)
    "haptics": True,               # a key tap vibrates (follows the system touch-feedback setting)
    "sound": False,                # a key tap clicks
    "auto_capitalize": True,       # shift at the start of a sentence, when the field asks for it
    "double_space_period": True,   # two spaces type ". "
}


def _native() -> bool:
    if platform() not in ("ios", "android"):   # the web and the desktop have no system keyboard to add
        return False
    require_linked("Keyboard", "keyboard", package="pyxpo-keyboard")
    return True


async def status_async() -> Dict[str, Any]:
    """Whether this app's keyboard exists on the platform (`supported`), is turned on in the system settings
    (`enabled`) and is the current keyboard (`selected`). `id` is the input method id on Android."""
    if not _native():
        return {"supported": False, "enabled": False, "selected": False, "id": ""}
    return await call("Keyboard", "status", reply=True)


async def open_settings_async() -> None:
    """Opens the system keyboard list (Android) or the app's Settings page (iOS)."""
    if _native():
        await call("Keyboard", "openSettings", reply=True)


async def show_picker_async() -> None:
    """Shows the system's keyboard chooser. Android only; it lists only keyboards that are turned on."""
    if platform() == "ios":
        raise NotSupportedError("show_picker_async is not supported on ios")
    if _native():
        await call("Keyboard", "showPicker", reply=True)


async def get_options_async() -> Dict[str, bool]:
    """The keyboard options (see `OPTIONS`)."""
    if platform() != "android" or not _native():
        return dict(OPTIONS)
    return await call("Keyboard", "getOptions", reply=True)


async def set_options_async(**options: bool) -> Dict[str, bool]:
    """Changes keyboard options, for example `set_options_async(number_row=True)`, and returns them all.
    The keyboard picks them up on the next field it opens in."""
    unknown = [k for k, v in options.items() if k not in OPTIONS or not isinstance(v, bool)]
    if unknown:
        raise ValueError("unknown or non-boolean keyboard options: %s (known: %s)"
                         % (", ".join(sorted(unknown)), ", ".join(OPTIONS)))
    if platform() == "ios":
        raise NotSupportedError("set_options_async is not supported on ios")
    if not _native():
        return {**OPTIONS, **options}
    return await call("Keyboard", "setOptions", options, reply=True)


statusAsync = status_async
openSettingsAsync = open_settings_async
showPickerAsync = show_picker_async
getOptionsAsync = get_options_async
setOptionsAsync = set_options_async

__all__ = [
    "OPTIONS", "status_async", "open_settings_async", "show_picker_async", "get_options_async",
    "set_options_async", "statusAsync", "openSettingsAsync", "showPickerAsync", "getOptionsAsync",
    "setOptionsAsync",
]
