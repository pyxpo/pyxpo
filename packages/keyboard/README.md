# pyxpo-keyboard

A system keyboard for [pyxpo](https://github.com/pyxpo/pyxpo) apps. Add this module and your Android app ships its
own keyboard. People can turn it on in Settings and type with it in every app on the phone. The keys are drawn and
handled in native Kotlin, so typing never waits for Python. Your app gets a few small calls to walk people through
turning the keyboard on and to change its options.

<p align="center">
  <img src="https://raw.githubusercontent.com/pyxpo/pyxpo-keyboard/main/docs/images/hero.png" width="820" alt="The AI Keyboard companion app on the Android emulator with the keyboard open: light theme, dark theme, and a password field marked private">
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
| Adding your own buttons (voice, AI) to the keyboard | [Toolbar buttons from your app](#toolbar-buttons-from-your-app) |
| Replacing the keys with a voice or AI screen | [App panel (voice screens)](#app-panel-voice-screens) |
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
  <img src="https://raw.githubusercontent.com/pyxpo/pyxpo-keyboard/main/docs/images/layouts.png" width="560" alt="The keyboard with the number row turned on, and the wide number pad it shows for a number field">
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

The keys follow the iOS look: lowercase letters until shift is on, round flat keys, line icons. The bottom row
has `123` (symbols), the emoji key, the globe (when the system offers switching), space, `@` or `/` in email and
web address fields, and `return` (or the field's action, such as Send, in the accent colour). Two spaces type
". ". The strip above the keys has a settings icon that hides the keyboard and opens your app, the status line
(or the private-field banner) and your app's buttons.

| Gesture | What it does |
| --- | --- |
| Tap shift | One capital letter. |
| Double tap or hold shift | Caps lock until shift is tapped again. |
| Hold a letter | Its alternate: the digit on the top row, a symbol on the others. |
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

## Toolbar buttons from your app

Android only. Your app can put up to 6 buttons in the keyboard's top strip, show a status line there, and type
text into the field. A tap starts your app's Python in the background when it is not running (no screen opens),
then calls your toolbar listeners. Register them at import time, in a module your root layout imports:

```python
import asyncio

import pyxpo_keyboard as Keyboard


async def say_hello(field):
    await Keyboard.set_status_async("Typing a greeting…")
    await Keyboard.commit_text_async("Hello from the app! ")
    await Keyboard.set_status_async("")


def on_tap(event):   # {"id": "hello", "field": {"kind": "text", "action": "Send", ...}}
    if event["id"] == "hello":
        asyncio.get_event_loop().create_task(say_hello(event["field"]))


Keyboard.add_toolbar_listener(on_tap)
```

Then set the buttons once, for example when the app opens (`use_async(set_buttons, [])`). The keyboard keeps
them, so they show before your Python runs:

```python
async def set_buttons():
    await Keyboard.set_toolbar_async([{"id": "hello", "label": "👋", "description": "Type a greeting"}])
```

| Button key | Type | Meaning |
| --- | --- | --- |
| `id` | `str` | Sent back in the tap event. Unique, not empty. |
| `label` | `str` | What the button shows: a short text or an emoji. |
| `icon` | `str` | A line icon drawn in place of the label, in the theme's colour: one of `Keyboard.ICONS` (`mic`, `sparkles`, `globe`, `smile`, `settings`). Optional. |
| `description` | `str` | Read by screen readers. Optional. |
| `active` | `bool` | Drawn highlighted, for example while recording. Optional, default `False`. |

| Call | What it does |
| --- | --- |
| `set_status_async(text)` | Shows `text` in the strip; `""` clears it. It resets when the keyboard opens on the next field. |
| `get_field_async()` | `{"kind", "action", "private", "multiline", "app"}` for the field the keyboard is in, or `None` while it is hidden. `kind` is `text`, `email`, `url`, `number`, `phone` or `datetime`; `app` is the other app's package name. Never the field's text. |
| `commit_text_async(text)` | Types `text` at the cursor (replacing a selection). |
| `get_text_async(before=1000, after=1000)` | `{"before", "selected", "after"}`: the text around the cursor, up to 10000 characters each side. |
| `add_input_listener(fn)` | `fn({"state": "start", "field": {...}})` when the keyboard opens on a field and `fn({"state": "finish"})` when it closes. Only while your Python is running. Use it to stop work the user walked away from. |

What stays private:

- In a [private field](#private-fields) the buttons are hidden, a tap cannot happen, and `commit_text_async` /
  `get_text_async` raise `RuntimeError`. The status line shows the private-field notice instead of yours.
- A tap event carries the button `id` and the field's kind, never its text. Your app reads text only by calling
  `get_text_async`, which the user's tap started.
- `commit_text_async` and `get_text_async` raise `RuntimeError` while the keyboard is hidden.

> **Tip:** without a screen, your app cannot ask for permissions. Ask in the app first (for example the
> microphone), and have the tap handler show a status line that sends the user there when one is missing.

## App panel (voice screens)

Android only. Your app can swap the keys and the toolbar for its own panel, at the same height: a round
microphone orb that pulses with the voice, text cards, a row of chips and up to four buttons. Call
`show_panel_async` again with the next spec to update it, and `hide_panel_async` to go back to the keys.

```python
import asyncio

import pyxpo_keyboard as Keyboard


def spec(said=""):
    return {
        "title": "Listening…" if not said else "Done",
        "hint": "Tap the orb when you finish",
        "orb": {"id": "mic", "state": "listening" if not said else "idle"},
        "sections": [{"id": "said", "label": "You said", "text": said, "placeholder": "Speak now",
                      "action": "Insert"}],
        "chips": [{"id": "hindi", "label": "Hindi", "active": True}, {"id": "english", "label": "English"}],
        "actions": [{"id": "cancel", "label": "Cancel"}, {"id": "done", "label": "Done", "primary": True}],
    }


def on_panel(event):   # {"type": "orb" | "section" | "chip" | "action" | "close" | "closed", "id": "..."}
    loop = asyncio.get_event_loop()
    if event["type"] == "action" and event["id"] == "cancel":
        loop.create_task(Keyboard.hide_panel_async())
    elif event["type"] == "section":
        loop.create_task(Keyboard.commit_text_async("hello "))


Keyboard.add_panel_listener(on_panel)
```

Open it from a toolbar tap (`await Keyboard.show_panel_async(spec())`) and feed the orb from
[`pyxpo-speech`](../speech/README.md)'s level listener with `Keyboard.set_panel_level(level)`, which does not wait.

| Spec key | Type | Meaning |
| --- | --- | --- |
| `title`, `hint` | `str` | The header lines. |
| `orb` | `dict` | `{"id", "state"}`; `state` is one of `ORB_STATES`: `idle` (a microphone), `listening` (pulses with the level, shows a stop square), `working` (spins), `error` (red). Big in the middle while no card has text, then small in the header. Optional. |
| `sections` | `list` | Up to 12 cards: `{"id", "label", "text", "placeholder", "busy", "action"}`. `busy` pulses the text; a card with an `action` label is tappable and sends `section`. |
| `chips` | `list` | Up to 16 pills in a scrolling row: `{"id", "label", "active", "busy"}`. |
| `actions` | `list` | Up to 4 buttons: `{"id", "label", "primary"}`. Primary ones are filled and wider. |

Every item needs a unique, non-empty `id`; chips and actions need a `label`. Unknown keys raise `ValueError`
before anything reaches the keyboard.

The panel listener gets `{"type", "id"}`: `orb`, `section`, `chip` or `action` with the item's id, `close`
when the user tapped **ABC** to go back to the keys, and `closed` when the keyboard closed it itself (the user
moved to another field, or the keyboard hid). Stop recording and drop any audio on `close` and `closed`.

What stays private: a panel never opens in a [private field](#private-fields) (`show_panel_async` raises
`RuntimeError`), and moving into one closes an open panel. Events carry ids only, never field text.

## Errors

| Error | When | What to do |
| --- | --- | --- |
| `ValueError` | `set_options_async` got an unknown option or a value that is not `True`/`False`; `set_toolbar_async` got a button without `id`/`label`, an unknown key or icon, a repeated id or more than 6 buttons; `get_text_async` got a count outside 0 to 10000. | Use the names in `OPTIONS` and pass real booleans; see [Toolbar buttons from your app](#toolbar-buttons-from-your-app). |
| `RuntimeError` | `commit_text_async` / `get_text_async` / `show_panel_async` while the keyboard is hidden or in a private field. | Call them from a toolbar tap; show the reason with `set_status_async` when they fail. |
| `NotSupportedError` (from `pyxpo.module_api`) | `show_picker_async()`, `set_options_async()` or a toolbar call on iOS; `commit_text_async()` / `get_text_async()` on the web and the desktop. | Check `status["supported"]` before showing those buttons. |
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
| `status_async() -> dict` | `{"supported", "enabled", "selected", "id"}`, plus `showing` on Android (the keyboard is open on a field). See [Setup flow](#setup-flow). |
| `open_settings_async() -> None` | Opens the system keyboard list (Android) or your app's Settings page (iOS). Does nothing on the web and the desktop. |
| `show_picker_async() -> None` | Opens the system keyboard chooser (Android). Raises `NotSupportedError` on iOS. Does nothing on the web and the desktop. |
| `get_options_async() -> dict` | All options. The defaults on iOS, the web and the desktop. |
| `set_options_async(**options) -> dict` | Changes the named options and returns all of them. Raises `ValueError` for unknown names or non-bool values, and `NotSupportedError` on iOS. |
| `set_toolbar_async(buttons) -> None` | Sets your toolbar buttons (Android). Does nothing on the web and the desktop. See [Toolbar buttons from your app](#toolbar-buttons-from-your-app). |
| `set_status_async(text) -> None` | The keyboard's status line (Android). |
| `get_field_async() -> dict or None` | The field the keyboard is in, without its text. `None` while hidden and off Android. |
| `commit_text_async(text) -> None` | Types text at the cursor. |
| `get_text_async(before=1000, after=1000) -> dict` | `{"before", "selected", "after"}` around the cursor. |
| `add_toolbar_listener(fn) -> remove` | `fn({"id", "field"})` on a button tap. |
| `add_input_listener(fn) -> remove` | `fn({"state": "start" or "finish", ...})` as the keyboard opens and closes on fields. |
| `show_panel_async(spec) -> None` | Shows or updates your panel in place of the keys (Android). Raises `ValueError` for a bad spec, `RuntimeError` while hidden or in a private field, `NotSupportedError` elsewhere. See [App panel](#app-panel-voice-screens). |
| `hide_panel_async() -> None` | Back to the keys. Does nothing off Android. |
| `set_panel_level(level) -> None` | The orb's pulse, 0 to 1. Not async; does nothing off Android. |
| `add_panel_listener(fn) -> remove` | `fn({"type", "id"})` on panel taps, `close` and `closed`. |
| `statusAsync`, `openSettingsAsync`, `showPickerAsync`, `getOptionsAsync`, `setOptionsAsync`, `setToolbarAsync`, `setStatusAsync`, `getFieldAsync`, `commitTextAsync`, `getTextAsync`, `addToolbarListener`, `addInputListener`, `showPanelAsync`, `hidePanelAsync`, `setPanelLevel`, `addPanelListener` | Expo-style names for the functions above. |

**Constants**

| Name | Description |
| --- | --- |
| `OPTIONS` | The option names and their defaults: `number_row`, `haptics`, `sound`, `auto_capitalize`, `double_space_period`. |
| `ICONS` | The line icons a toolbar button can use as `icon`: `mic`, `sparkles`, `globe`, `smile`, `settings`. |
| `ORB_STATES` | The panel orb states: `idle`, `listening`, `working`, `error`. |

## License

MIT. The screenshots show the AI Keyboard companion app running on the Android emulator.
