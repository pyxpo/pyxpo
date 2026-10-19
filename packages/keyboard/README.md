# pyxpo-keyboard

A system keyboard for [pyxpo](https://github.com/pyxpo/pyxpo) apps. Add this module and your Android app ships its
own keyboard. People can turn it on in Settings and type with it in every app on the phone. The keys are drawn and
handled in native Kotlin, so typing never waits for Python. Your app gets a few small calls to walk people through
turning the keyboard on and to change its options.

<p align="center">
  <img src="https://raw.githubusercontent.com/pyxpo/pyxpo/main/packages/keyboard/docs/images/hero.png" width="820" alt="The AI Keyboard companion app on the Android emulator with the keyboard open: light theme, dark theme, and a password field marked private">
</p>

```python
import pyxpo_keyboard as Keyboard

s = await Keyboard.status_async()             # {"supported", "enabled", "selected", "id"}
if not s["enabled"]:
    await Keyboard.open_settings_async()      # the system keyboard list: the user switches yours on
elif not s["selected"]:
    await Keyboard.show_picker_async()        # the system "choose keyboard" dialog
await Keyboard.set_options_async(number_row=True, haptics=False)
```

## Features

- **A real system keyboard:**
  - Android `InputMethodService`, listed under your app's name in Settings > Keyboards.
  - Works in every app, not only your own.
  - No extra Gradle dependencies, and no network calls.
- **Native keys:**
  - QWERTY letters, two symbol pages, a number pad and a phone pad, each picked from the field's input type.
  - Email fields get an `@` key and URL fields a `/` key.
  - Shift: tap once for one capital, double tap for caps lock, hold for caps lock.
  - Hold a key to type its alternate (digits on the top row, symbols on the others). Delete repeats while held.
  - The enter key shows the field's action (Go, Search, Send, Next, Done) and runs it.
  - There is an emoji panel. The 🌐 key switches to the next keyboard; holding space opens the system keyboard
    chooser.
- **Follows the phone:**
  - Light and dark themes, which switch live while the keyboard is open.
  - Keys stay above the navigation bar on edge-to-edge Android 15+.
  - Taps vibrate through the system touch-feedback setting.
- **Private fields:**
  - Password, numeric PIN and incognito fields are marked private.
  - A 🔒 banner tells the user that AI and voice features are off there.
- **Options from Python:** number row, vibrate, click sound, auto-capitals, double-space period. They are kept
  across restarts, and the keyboard reads them on the next field it opens.
- **Typed:** ships `py.typed`. Expo-style camelCase names (`statusAsync`, ...) work too.

## Contents

| If you are... | Start here |
| --- | --- |
| Adding a keyboard to your app | [Install](#install) → [Quick start](#quick-start) |
| Walking people through setup | [Setup flow](#setup-flow) |
| Wondering which keys show where | [The keys](#the-keys) · [Private fields](#private-fields) |
| Changing how it types | [Options](#options) |
| Seeing it in a real app | [Recipe: a setup screen that keeps up with Settings](#recipe-a-setup-screen-that-keeps-up-with-settings) |
| Shipping to the stores | [Production checklist](#production-checklist) |
| Looking for exact signatures | [API reference](#api-reference) · [Errors](#errors) |
| Stuck | [Testing](#testing) · [Troubleshooting](#troubleshooting) · [FAQ](#faq) |

## Platform support

| Target | Keyboard |
| --- | --- |
| Android, API 24+ | The full keyboard and all calls. The 🌐 key needs API 28+. Light/dark switching while the keyboard is open needs API 34+; on older versions the system rebuilds the keyboard instead. |
| iOS | Not yet. iOS keyboards are app extensions, which this version does not add. `status_async()` returns `supported: False`, `open_settings_async()` opens your app's page in Settings, `get_options_async()` returns the defaults, and `show_picker_async()` / `set_options_async()` raise `NotSupportedError`. |
| Web page and desktop window (`pyxpo run web` / `pyxpo run desktop`), Mac Catalyst, Windows | No keyboard. Every call returns the defaults and does nothing (see [Web and desktop](#web-and-desktop)). |

Requires Python 3.9+ and `pyxpo>=0.1.0a2`.

## Install

```sh
pip install pyxpo-keyboard
```

Add the module to your app's `pyproject.toml`:

```toml
[tool.pyxpo]
modules = ["keyboard"]
```

The package has no config plugin and no options to set at build time. When the module is linked, it adds the
following to the Android manifest:

- The input method service, bound with `BIND_INPUT_METHOD`, using your app's name as its label.
- The `VIBRATE` permission, needed for tap feedback. It is a normal permission, so Android never asks the user for it.

The module has native code, so rebuild the app after adding it (`pyxpo run android`).

## Quick start

A screen that tells people what to do next, and checks again whenever they come back from Settings:

```python
import pyxpo_keyboard as Keyboard
from pyxpo import AppState, Pressable, Text, TextInput, View, component, use_async, use_effect, use_state


@component
def KeyboardSetup():
    tick, set_tick = use_state(0)
    status = use_async(Keyboard.status_async, [tick])

    def watch():   # Settings is another app: check again when the user comes back
        sub = AppState.addEventListener("change", lambda s: set_tick(lambda t: t + 1) if s == "active" else None)
        return sub.remove
    use_effect(watch, [])

    s = status.value
    if s is None:
        return Text("Checking...")
    if not s["supported"]:
        return Text("This keyboard works on Android.")
    if not s["enabled"]:
        step = Pressable(Text("Turn on the keyboard"), on_press=lambda: Keyboard.open_settings_async())
    elif not s["selected"]:
        step = Pressable(Text("Choose it"), on_press=lambda: Keyboard.show_picker_async())
    else:
        step = Text("All set. Try it below.")
    return View(
        step,
        TextInput(placeholder="Type here", style={"borderWidth": 1, "borderRadius": 12, "padding": 12}),
        style={"flex": 1, "justifyContent": "center", "padding": 24, "gap": 16},
    )
```

> **Tip:** Picking a keyboard in the chooser does not leave your app, so `AppState` does not fire. The
> [recipe](#recipe-a-setup-screen-that-keeps-up-with-settings) checks again every second while the keyboard is on
> but not chosen yet.

## Setup flow

Android does not let an app turn on its own keyboard. The user does it in two steps, and your app can open the
right system screen for each one.

| Step | Check | Call | What the user sees |
| --- | --- | --- | --- |
| 1. Turn it on | `status["enabled"]` | `open_settings_async()` | The system list of keyboards. They switch yours on and accept Android's warning that a keyboard can read what they type. |
| 2. Choose it | `status["selected"]` | `show_picker_async()` | The system "Choose input method" dialog. It lists only keyboards that are turned on, so step 1 comes first. |

`status_async()` returns:

| Key | Type | Meaning |
| --- | --- | --- |
| `supported` | `bool` | The platform can run this keyboard. True on Android only. |
| `enabled` | `bool` | The user turned it on in Settings. |
| `selected` | `bool` | It is the current keyboard. |
| `id` | `str` | The Android input method id, for example `com.example.app/dev.pyxpo.modules.keyboard.KeyboardService`. Empty elsewhere. Useful with `adb shell ime set`. |

Every user decides for themselves. Your app cannot skip either step, and the status can change at any time, for
example when the user picks another keyboard. Call `status_async()` again whenever your screen comes back into
view.

## The keys

<p align="center">
  <img src="https://raw.githubusercontent.com/pyxpo/pyxpo/main/packages/keyboard/docs/images/layouts.png" width="560" alt="The keyboard with the number row turned on, and the wide number pad it shows for a number field">
</p>

The keyboard picks a layout from the field it types into. A pyxpo `TextInput` sets the field type through its props;
other apps set it through their own input types.

| Field | `TextInput` props | Layout |
| --- | --- | --- |
| Text | (default), `multiline=True` | QWERTY with `,` next to the toggle key. In a multi-line field, enter adds a new line. |
| Email | `keyboard_type="email-address"` | QWERTY with `@` in place of `,`. |
| URL | `keyboard_type="url"` | QWERTY with `/` in place of `,`. |
| Number | `keyboard_type="number-pad"`, `"decimal-pad"`, `"numeric"` | A full-width number pad. |
| Phone | `keyboard_type="phone-pad"` | A phone pad. |
| Password | `secure_text_entry=True` | QWERTY, marked private (see below). |

The bottom row has `?123` (symbols), the field key (`,`, `@` or `/`), 🌐 (when the system offers switching), 😊
(emoji panel), space, `.` (hold for `?`) and enter. The strip above the keys has the private-field banner and a ⚙
key that hides the keyboard and opens your app.

| Gesture | What it does |
| --- | --- |
| Tap shift | One capital letter. |
| Double tap or hold shift | Caps lock until shift is tapped again. |
| Hold a letter | Its alternate: the digit on the top row, a symbol on the others (shown in the key's corner). |
| Hold delete | Repeats. Removes a whole emoji at a time. |
| Hold space | Opens the system keyboard chooser. |
| Tap 🌐 | Switches to the next keyboard. |
| Two spaces after a word | `. ` (when `double_space_period` is on). |

Auto-capitals follow the field: a capital letter starts a sentence only when the field asks for it, for example
`auto_capitalize="sentences"`. A field with `auto_capitalize="none"`, as most email fields have, never gets one.

## Private fields

The keyboard marks these fields private:

- Text passwords: `TYPE_TEXT_VARIATION_PASSWORD`, `VISIBLE_PASSWORD` and `WEB_PASSWORD`. A pyxpo `TextInput` with
  `secure_text_entry=True` is one of them.
- Numeric PINs: `TYPE_NUMBER_VARIATION_PASSWORD`.
- Any field that sets `IME_FLAG_NO_PERSONALIZED_LEARNING`, which is what browsers use for incognito tabs.

In a private field, the strip shows "🔒 Private field: AI and voice are off". The keyboard itself never keeps or
sends any text, in any field. Its only stored state is the options below.

## Options

```python
opts = await Keyboard.get_options_async()                  # {"number_row": False, "haptics": True, ...}
opts = await Keyboard.set_options_async(number_row=True)   # returns all options after the change
```

| Option | Default | What it does |
| --- | --- | --- |
| `number_row` | `False` | A row of digits above the letters. When it is off, hold a top-row letter for its digit. |
| `haptics` | `True` | Each tap vibrates. Follows the system touch-feedback setting: if that is off, nothing vibrates. |
| `sound` | `False` | Each tap clicks. |
| `auto_capitalize` | `True` | Shift turns on at the start of a sentence, when the field asks for it. |
| `double_space_period` | `True` | Two spaces after a word type `. `. |

- Options are stored in the app's private preferences. They survive restarts but not "Clear storage".
- The keyboard reads them each time it opens on a field, so a change shows up on the next field the user taps.
- `set_options_async` checks names and types in Python first. An unknown name or a value that is not a `bool`
  raises `ValueError`, and nothing is changed.
- `OPTIONS` holds the defaults.

## Errors

| Error | When | What to do |
| --- | --- | --- |
| `ValueError` | `set_options_async` got an unknown option or a value that is not `True`/`False`. | Use the names in `OPTIONS` and pass real booleans. |
| `NotSupportedError` (from `pyxpo.module_api`) | `show_picker_async()` or `set_options_async()` on iOS. | Check `status["supported"]` before showing those buttons. |
| `ModuleNotLinkedError` (from `pyxpo.module_api`) | An Android or iOS app built without the module. | Add `"keyboard"` to `[tool.pyxpo] modules` and rebuild. |

## Web and desktop

There is no system keyboard to add on the web, the desktop, Mac Catalyst or Windows:

- `status_async()` returns `{"supported": False, "enabled": False, "selected": False, "id": ""}`.
- `get_options_async()` returns the defaults.
- `set_options_async(...)` returns the defaults with your changes applied, but stores nothing.
- `open_settings_async()` and `show_picker_async()` do nothing.

Option names and values are still checked on these targets, so a typo shows up in the browser too. The Quick start
screen above shows "This keyboard works on Android." in these builds.

## Recipe: a setup screen that keeps up with Settings

This is how the AI Keyboard companion app (shown in the pictures) builds its setup screen:

- The last status stays on screen while the next one loads, so the steps do not flicker.
- It checks again when the app comes back from Settings.
- While the keyboard is on but not chosen yet, it checks again every second, because the chooser dialog does not
  leave the app.

```python
import asyncio

import pyxpo_keyboard as Keyboard
from pyxpo import (AppState, Pressable, ScrollView, Switch, Text, TextInput, View, component, use_async, use_effect,
                   use_state)

OPTION_LABELS = [
    ("number_row", "Number row"),
    ("haptics", "Vibrate on tap"),
    ("sound", "Sound on tap"),
    ("auto_capitalize", "Auto capitals"),
    ("double_space_period", "Double-space period"),
]


@component
def Setup():
    tick, set_tick = use_state(0)
    status, set_status = use_state({})

    def refresh():   # keeps the last status while the next one loads
        task = asyncio.ensure_future(Keyboard.status_async())
        task.add_done_callback(lambda t: set_status(t.result()) if not t.cancelled() and not t.exception() else None)
        return task.cancel
    use_effect(refresh, [tick])

    def subscribe():
        sub = AppState.addEventListener("change", lambda s: set_tick(lambda t: t + 1) if s == "active" else None)
        return sub.remove
    use_effect(subscribe, [])

    enabled, selected = status.get("enabled", False), status.get("selected", False)

    def recheck():   # the chooser dialog does not leave the app, so AppState never fires for it
        if not (enabled and not selected):
            return None
        task = asyncio.ensure_future(asyncio.sleep(1))
        task.add_done_callback(lambda t: None if t.cancelled() else set_tick(lambda n: n + 1))
        return task.cancel
    use_effect(recheck, [enabled, selected, tick])

    loaded = use_async(Keyboard.get_options_async, []).value
    options, set_options = use_state(None)
    shown = options or loaded or Keyboard.OPTIONS

    async def toggle(name, value):
        set_options(await Keyboard.set_options_async(**{name: value}))

    if not status.get("supported", True):
        return Text("This keyboard works on Android.")
    return ScrollView(
        Text("1. Turn on the keyboard " + ("✓" if enabled else "")),
        Pressable(Text("Open keyboard settings"), on_press=lambda: Keyboard.open_settings_async())
        if not enabled else None,
        Text("2. Choose it " + ("✓" if selected else "")),
        Pressable(Text("Choose keyboard"), on_press=lambda: Keyboard.show_picker_async())
        if enabled and not selected else None,
        TextInput(placeholder="Message", multiline=True, auto_capitalize="sentences"),
        TextInput(placeholder="Password", secure_text_entry=True),
        *[View(Text(label, style={"flex": 1}),
               Switch(value=bool(shown.get(name)), on_value_change=lambda v, n=name: toggle(n, v)),
               key=name, style={"flexDirection": "row", "alignItems": "center"})
          for name, label in OPTION_LABELS],
        content_container_style={"padding": 20, "gap": 12},
        keyboard_should_persist_taps="handled",
    )
```

## Production checklist

- Explain why people should turn the keyboard on before you send them to Settings. Android shows a strong warning
  ("this input method may be able to collect all the text you type"), so say plainly what your keyboard keeps and
  sends.
- Re-check `status_async()` when your screen comes back into view. The user can switch keyboards at any time.
- Never store or send typed text from your own keyboard code, and treat private fields as off-limits for any feature
  you add later.
- Google Play's User Data policy covers keyboards: declare in the data safety form what the keyboard collects (this package collects nothing),
  and keep a privacy policy that covers it.
- Test with apps you did not write: a browser address bar, a chat app, a password manager, a PIN pad.
- Test light and dark mode, large font sizes, and a phone with gesture navigation and one with three-button
  navigation.
- Hide the setup steps on iOS, the web and the desktop (`status["supported"]` is False there).

## Testing

**On the Android emulator**, after installing the app, you can turn the keyboard on and choose it without tapping
through Settings. `adb` prints the id that `status_async()` returns:

```sh
adb shell ime list -a -s | grep KeyboardService
adb shell ime enable com.example.app/dev.pyxpo.modules.keyboard.KeyboardService
adb shell ime set com.example.app/dev.pyxpo.modules.keyboard.KeyboardService
adb shell cmd uimode night yes   # switch to dark mode while the keyboard is open
```

Reinstalling the app can switch the phone back to its default keyboard. Run `ime set` again after each install.

**Unit tests** run without a device. `pyxpo.module_testing.FakeBridge` pretends to be the native side, so you can
script each step of the setup:

```python
import asyncio

import pyxpo_keyboard as Keyboard
from pyxpo.module_testing import FakeBridge


def test_setup_goes_to_the_chooser_once_enabled():
    with FakeBridge("android") as fb:
        fb.on("Keyboard", "status", lambda: {"supported": True, "enabled": True, "selected": False, "id": "x"})
        fb.on("Keyboard", "showPicker", lambda: None)
        status = asyncio.run(Keyboard.status_async())
        if status["enabled"] and not status["selected"]:
            asyncio.run(Keyboard.show_picker_async())
        assert [c[1] for c in fb.calls] == ["status", "showPicker"]
```

Without a `FakeBridge`, the calls behave as on the desktop and return the defaults. A screen test can also
`monkeypatch.setattr(Keyboard, "status_async", fake)` with an `async def fake()`.

## Troubleshooting

| Problem | Cause and fix |
| --- | --- |
| The keyboard is not in Settings > Keyboards | The build does not include the module. Add `"keyboard"` to `[tool.pyxpo] modules` and rebuild; check with `adb shell ime list -a -s`. |
| "Choose keyboard" shows a dialog without your keyboard | It is not turned on yet. The chooser lists only enabled keyboards; do step 1 first. |
| The setup screen still says "not chosen" after picking it | The chooser does not leave your app, so `AppState` does not fire. Check again on a timer while `enabled and not selected` (see the [recipe](#recipe-a-setup-screen-that-keeps-up-with-settings)). |
| The phone went back to its old keyboard after a reinstall | Android resets the current keyboard when its app is replaced. Choose it again (`adb shell ime set ...` on the emulator). |
| An option change does not show up | The keyboard reads options when it opens on a field. Tap into another field, or close and reopen the keyboard. |
| No vibration on tap | `haptics` follows the system "Touch feedback" setting. Turn that on, or check that the emulator or phone has a vibrator. |
| Two keyboard-switch buttons | Android can show its own keyboard button in the navigation bar as well as the 🌐 key. Both switch keyboards; the system button cannot be hidden by the keyboard. |
| `NotSupportedError` on iOS | iOS keyboards need an app extension, which this version does not add. Check `status["supported"]`. |
| `ModuleNotLinkedError` | The app was built without the module. Add it to `[tool.pyxpo] modules` and rebuild. |
| `RuntimeWarning: coroutine ... was never awaited` | The call was started with `use_effect(lambda: coro())`. Use `use_async(Keyboard.status_async, [...])`, or `asyncio.ensure_future` as in the recipe. |

## FAQ

**Does the keyboard see or keep what people type?**
It handles each key press to type the character into the field, the same as any keyboard. It does not store, log or
send text. The only data it keeps is the five options.

**Does typing go through Python?**
No. Keys, layouts, shift and feedback all run in Kotlin inside the keyboard service, so typing does not wait for the
Python runtime. Your app's Python code only runs the setup and options calls.

**Can I change the key layout or colours?**
Not in this version. The keyboard follows the phone's light or dark theme. Layouts for other languages are planned.

**Is there voice typing or AI writing?**
Not in this package. The private-field flag is there so that apps adding these features can keep them off in
passwords and PINs.

**When does iOS get a keyboard?**
That needs a keyboard app extension in the iOS build, which is planned. Until then, `status_async()` reports
`supported: False` on iOS.

## API reference

**Functions**

| Name | Description |
| --- | --- |
| `status_async() -> dict` | `{"supported", "enabled", "selected", "id"}`. See [Setup flow](#setup-flow). |
| `open_settings_async() -> None` | Opens the system keyboard list (Android) or your app's Settings page (iOS). Does nothing on the web and the desktop. |
| `show_picker_async() -> None` | Opens the system keyboard chooser (Android). Raises `NotSupportedError` on iOS. Does nothing on the web and the desktop. |
| `get_options_async() -> dict` | All options. The defaults on iOS, the web and the desktop. |
| `set_options_async(**options) -> dict` | Changes the named options and returns all of them. Raises `ValueError` for unknown names or non-bool values, and `NotSupportedError` on iOS. |
| `statusAsync`, `openSettingsAsync`, `showPickerAsync`, `getOptionsAsync`, `setOptionsAsync` | Expo-style names for the functions above. |

**Constants**

| Name | Description |
| --- | --- |
| `OPTIONS` | The option names and their defaults: `number_row`, `haptics`, `sound`, `auto_capitalize`, `double_space_period`. |

## License

MIT. The screenshots show the AI Keyboard companion app running on the Android emulator.
