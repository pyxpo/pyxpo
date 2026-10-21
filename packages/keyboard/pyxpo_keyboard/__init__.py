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

The app can add its own buttons to the keyboard's toolbar (Android). The keyboard starts the app's Python
in the background when one is tapped, even with the app closed, and calls the toolbar listeners:

    Keyboard.add_toolbar_listener(on_tap)                       # on_tap({"id": "mic", "field": {...}})
    await Keyboard.set_toolbar_async([{"id": "mic", "label": "🎤", "description": "Voice typing"}])
    await Keyboard.set_status_async("Listening…")
    await Keyboard.commit_text_async("Hello there ")            # typed at the cursor

Private fields never show the buttons, and the keyboard refuses to read or type app text in them.

The app can also replace the keys with its own panel (Android), for example a voice screen: a microphone
orb that pulses with the voice, text cards, chips and buttons. Taps come back to the panel listeners:

    Keyboard.add_panel_listener(on_panel)                       # on_panel({"type": "chip", "id": "warm"})
    await Keyboard.show_panel_async({"title": "Listening…", "orb": {"id": "mic", "state": "listening"},
                                     "actions": [{"id": "done", "label": "Done", "primary": True}]})
    Keyboard.set_panel_level(0.4)                                # the orb's pulse, 0..1
    await Keyboard.hide_panel_async()                            # back to the keys
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from pyxpo.module_api import NotSupportedError, call, on_event, platform, require_linked

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


# the app's toolbar buttons, status line and the field (Android, while the keyboard is up)

def _android(what: str) -> bool:
    if platform() == "ios":
        raise NotSupportedError("%s is not supported on ios" % what)
    return platform() == "android" and _native()


#: Line icons the keyboard draws itself (crisp at any size, tinted to the theme), for a button's `icon`.
ICONS = ("mic", "sparkles", "globe", "smile", "settings")


def _button(b: Any) -> Dict[str, Any]:
    if not isinstance(b, dict):
        raise ValueError("a toolbar button is a dict with 'id' and 'label', not %r" % (b,))
    unknown = set(b) - {"id", "label", "description", "active", "icon"}
    if unknown:
        raise ValueError("unknown toolbar button keys: %s" % ", ".join(sorted(unknown)))
    bid, label = b.get("id"), b.get("label")
    if not (isinstance(bid, str) and bid and isinstance(label, str) and label):
        raise ValueError("a toolbar button needs a non-empty 'id' and 'label'")
    icon = b.get("icon") or ""
    if icon and icon not in ICONS:
        raise ValueError("unknown toolbar icon %r: use one of %s" % (icon, ", ".join(ICONS)))
    return {"id": bid, "label": label, "description": str(b.get("description") or ""),
            "active": bool(b.get("active", False)), "icon": icon}


async def set_toolbar_async(buttons: List[Dict[str, Any]]) -> None:
    """Sets the app's toolbar buttons: dicts with `id`, `label` (a short text or emoji), and optional
    `description` (for screen readers), `active` (drawn highlighted, for example while recording) and `icon`
    (one of `ICONS`, drawn as a line icon in place of the label; the label stays the screen reader's fallback).
    The keyboard keeps them, so they show before the app's Python runs. Up to 6; `[]` removes them."""
    out = [_button(b) for b in buttons]
    if len(out) > 6:
        raise ValueError("the toolbar has room for 6 buttons")
    if len({b["id"] for b in out}) != len(out):
        raise ValueError("toolbar button ids must be unique")
    if _android("set_toolbar_async"):
        await call("Keyboard", "setToolbar", out, reply=True)


async def set_status_async(text: str) -> None:
    """Shows a short line in the keyboard's toolbar (`""` clears it). It resets on the next field."""
    if _android("set_status_async"):
        await call("Keyboard", "setStatus", str(text), reply=True)


async def get_field_async() -> Optional[Dict[str, Any]]:
    """The field the keyboard types in, or None while it is hidden: `kind` (text, email, url, number, phone,
    datetime), `action` (the enter key's label, or None), `private`, `multiline` and `app` (the package name).
    Never the field's text."""
    if not _android("get_field_async"):
        return None
    return await call("Keyboard", "field", reply=True)


async def commit_text_async(text: str) -> None:
    """Types `text` at the cursor (replacing a selection). Raises `RuntimeError` when the keyboard is hidden
    or the field is private."""
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    if not _android("commit_text_async"):
        raise NotSupportedError("commit_text_async needs the Android keyboard")
    await call("Keyboard", "commitText", text, reply=True)


async def get_text_async(before: int = 1000, after: int = 1000) -> Dict[str, str]:
    """The field's text around the cursor: `before`, `selected` and `after` (up to `before`/`after`
    characters, at most 10000). Raises `RuntimeError` when the keyboard is hidden or the field is private."""
    for n in (before, after):
        if not (isinstance(n, int) and 0 <= n <= 10000):
            raise ValueError("before and after must be 0 to 10000")
    if not _android("get_text_async"):
        raise NotSupportedError("get_text_async needs the Android keyboard")
    return await call("Keyboard", "getText", {"before": before, "after": after}, reply=True)


# the app's panel in place of the keys

#: The orb's states: idle (a microphone), listening (pulses with `set_panel_level`), working (spins), error.
ORB_STATES = ("idle", "listening", "working", "error")

_PANEL_KEYS = {"title", "hint", "orb", "sections", "chips", "actions"}
_PANEL_ITEMS = {
    "sections": ({"id", "label", "text", "placeholder", "busy", "action"}, 12),
    "chips": ({"id", "label", "active", "busy"}, 16),
    "actions": ({"id", "label", "primary"}, 4),
}


def _panel(spec: Any) -> Dict[str, Any]:
    if not isinstance(spec, dict):
        raise ValueError("a panel is a dict, not %r" % (spec,))
    unknown = set(spec) - _PANEL_KEYS
    if unknown:
        raise ValueError("unknown panel keys: %s" % ", ".join(sorted(unknown)))
    out: Dict[str, Any] = {"title": str(spec.get("title") or ""), "hint": str(spec.get("hint") or "")}
    orb = spec.get("orb")
    if orb is not None:
        if not isinstance(orb, dict) or set(orb) - {"id", "state"}:
            raise ValueError("the panel's orb is a dict with 'id' and 'state'")
        state = orb.get("state", "idle")
        if state not in ORB_STATES:
            raise ValueError("orb state must be one of %s, not %r" % (", ".join(ORB_STATES), state))
        out["orb"] = {"id": str(orb.get("id") or ""), "state": state}
    for key, (allowed, most) in _PANEL_ITEMS.items():
        items = spec.get(key) or []
        if not isinstance(items, (list, tuple)):
            raise ValueError("panel %s must be a list" % key)
        if len(items) > most:
            raise ValueError("a panel has room for %d %s" % (most, key))
        clean = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("panel %s are dicts, not %r" % (key, item))
            bad = set(item) - allowed
            if bad:
                raise ValueError("unknown keys in panel %s: %s" % (key, ", ".join(sorted(bad))))
            iid = item.get("id")
            if not (isinstance(iid, str) and iid):
                raise ValueError("panel %s need a non-empty 'id'" % key)
            if key != "sections" and not item.get("label"):
                raise ValueError("panel %s need a 'label'" % key)
            clean.append({k: (bool(v) if k in ("busy", "active", "primary") else str(v if v is not None else ""))
                          for k, v in item.items()})
        if len({i["id"] for i in clean}) != len(clean):
            raise ValueError("panel %s ids must be unique" % key)
        out[key] = clean
    return out


async def show_panel_async(spec: Dict[str, Any]) -> None:
    """Shows the app's panel in place of the keys and the toolbar, or updates it (call it again with the next
    spec). The keyboard keeps its height. `spec`:

    - `title`, `hint`: the header lines.
    - `orb`: `{"id", "state"}`, a round microphone button (see `ORB_STATES`). Big in the middle while no section
      has text, then small in the header.
    - `sections`: up to 12 cards, `{"id", "label", "text", "placeholder", "busy", "action"}`. `busy` pulses the
      text; a card with an `action` label is tappable.
    - `chips`: up to 16 pills in a scrolling row, `{"id", "label", "active", "busy"}`.
    - `actions`: up to 4 buttons along the bottom, `{"id", "label", "primary"}`.

    Taps go to `add_panel_listener`. Raises `RuntimeError` when the keyboard is hidden or the field is private.
    The keyboard closes the panel itself when the field changes or the keyboard hides (listeners get `closed`)."""
    clean = _panel(spec)
    if not _android("show_panel_async"):
        raise NotSupportedError("show_panel_async needs the Android keyboard")
    await call("Keyboard", "showPanel", clean, reply=True)


async def hide_panel_async() -> None:
    """Back to the keys."""
    if _android("hide_panel_async"):
        await call("Keyboard", "hidePanel", reply=True)


def set_panel_level(level: float) -> None:
    """Sets how far the orb pulses while `listening`, 0 (quiet) to 1. Does not wait: call it with every
    `pyxpo_speech` level."""
    if platform() == "android" and _native():
        call("Keyboard", "setPanelLevel", max(0.0, min(1.0, float(level))))


def add_panel_listener(listener: Callable[[Dict[str, Any]], Any]) -> Callable[[], None]:
    """Calls `listener({"type", "id"})` for taps on the panel: `orb`, `section`, `chip` or `action` with the
    item's id, `close` when the user went back to the keys, and `closed` when the keyboard closed it (another
    field, or the keyboard hid). Returns a remove function. Register it at import time."""
    return on_event("Keyboard.panel", lambda d: listener(dict(d or {})))


def add_toolbar_listener(listener: Callable[[Dict[str, Any]], Any]) -> Callable[[], None]:
    """Calls `listener({"id", "field"})` when a toolbar button is tapped (`field` as in `get_field_async`,
    without `app`). Returns a remove function. Register it at import time: a tap can start the app's Python."""
    return on_event("Keyboard.toolbar", lambda d: listener(dict(d or {})))


def add_input_listener(listener: Callable[[Dict[str, Any]], Any]) -> Callable[[], None]:
    """Calls `listener({"state": "start", "field": {...}})` when the keyboard opens in a field and
    `{"state": "finish"}` when it closes (only while the app's Python is running). Returns a remove function."""
    return on_event("Keyboard.input", lambda d: listener(dict(d or {})))


statusAsync = status_async
openSettingsAsync = open_settings_async
showPickerAsync = show_picker_async
getOptionsAsync = get_options_async
setOptionsAsync = set_options_async
setToolbarAsync = set_toolbar_async
setStatusAsync = set_status_async
getFieldAsync = get_field_async
commitTextAsync = commit_text_async
getTextAsync = get_text_async
addToolbarListener = add_toolbar_listener
addInputListener = add_input_listener
showPanelAsync = show_panel_async
hidePanelAsync = hide_panel_async
setPanelLevel = set_panel_level
addPanelListener = add_panel_listener

__all__ = [
    "OPTIONS", "status_async", "open_settings_async", "show_picker_async", "get_options_async",
    "set_options_async", "statusAsync", "openSettingsAsync", "showPickerAsync", "getOptionsAsync",
    "setOptionsAsync", "set_toolbar_async", "set_status_async", "get_field_async", "commit_text_async",
    "get_text_async", "add_toolbar_listener", "add_input_listener", "setToolbarAsync", "setStatusAsync",
    "getFieldAsync", "commitTextAsync", "getTextAsync", "addToolbarListener", "addInputListener",
    "ORB_STATES", "show_panel_async", "hide_panel_async", "set_panel_level", "add_panel_listener",
    "showPanelAsync", "hidePanelAsync", "setPanelLevel", "addPanelListener",
]
