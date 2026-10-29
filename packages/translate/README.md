# pyxpo-translate

Offline text translation for [pyxpo](https://github.com/pyxpo/pyxpo) apps, written in Python. It runs Google ML
Kit's on-device translation models on Android: the app downloads a language model once (about 30 MB) when the user
agrees, and from then on every translation runs on the phone, with no network, account or API key. About 60
languages, including Hindi, Spanish, Chinese, Arabic and French.

<p align="center">
  <img src="https://raw.githubusercontent.com/pyxpo/pyxpo-translate/main/docs/images/hero.png" width="820" alt="A pyxpo demo on Android downloading the Hindi model, then translating a Hindi sentence to English offline">
</p>

```python
import pyxpo_translate as Translate

if not await Translate.is_ready_async("hi", "en"):
    await Translate.download_async("hi")                  # once, after the user agrees
english = await Translate.translate_async("मैं कल आऊँगा", "hi", "en")   # "I will come tomorrow"
```

## Features

- **Offline after one download:**
  - `download_async(language)` fetches one language's model from Google, once.
  - `translate_async` then runs on the phone. It never fetches a model by itself: a missing language raises an
    error at once instead of waiting on the network.
  - English is built in and never downloaded.
- **Private:** the text you translate is never sent anywhere and never logged. Only model files come from the
  network, and only when you call `download_async`.
- **The app decides when to download:** `is_ready_async`, `downloaded_async` and `status_async` tell you what is on
  the phone, so you can ask the user first, and `wifi_only=True` waits for Wi-Fi instead of using mobile data.
- **Fast after the first call:** the first translation of a language pair loads its model (about a second); the
  module keeps it open for the next call. `close_async()` frees the memory.
- **Works from a keyboard:** the module needs no screen, so an input method built with `pyxpo-keyboard` can call
  it (the [recipe](#recipe-a-voice-keyboard-that-types-english) shows one).
- **Checked arguments:** language codes and text are checked in Python before any native work starts.

## Contents

| If you are... | Start here |
| --- | --- |
| New to the package | [Quick start](#quick-start) → [Languages](#languages) |
| Getting models onto the phone | [Downloading models](#downloading-models) |
| Translating text | [Translating](#translating) |
| Seeing it in a real app | [Recipe: a voice keyboard that types English](#recipe-a-voice-keyboard-that-types-english) |
| Shipping to the stores | [Production checklist](#production-checklist) |
| Looking for exact signatures | [API reference](#api-reference) · [Errors](#errors) |
| Stuck | [Testing](#testing) · [Troubleshooting](#troubleshooting) · [FAQ](#faq) |

## Platform support

| Target | Translation |
| --- | --- |
| Android, API 24+ | Yes. Google ML Kit on-device translation (`com.google.mlkit:translate`). Models download on request. |
| iOS | Not yet. `status_async()` reports `supported: False` and the other calls raise `NotSupportedError`. |
| Web page and desktop window (`pyxpo run web` / `pyxpo run desktop`), Mac Catalyst, Windows | None, same as iOS. |

Requires Python 3.9+ and `pyxpo>=0.1.0a6`.

## Install

```sh
pip install pyxpo-translate
```

Add the module to your app's `pyproject.toml`:

```toml
[tool.pyxpo]
modules = ["translate"]
```

The package has no config plugin and no options. Its Android manifest adds the `INTERNET` and
`ACCESS_NETWORK_STATE` permissions, which `download_async` needs to fetch models. If your app said it uses no
network, update that text: the app now downloads model files when asked (the text it translates still stays on the
phone).

The module has native code, so rebuild the app after adding it (`pyxpo run android`). The first build downloads ML
Kit through Gradle.

## Quick start

A screen that downloads the Hindi model when the user taps, then translates what they type:

```python
import pyxpo_translate as Translate
from pyxpo import Pressable, Text, TextInput, View, component, use_async, use_state


@component
def HindiToEnglish():
    ready = use_async(lambda: Translate.is_ready_async("hi", "en"), [])
    downloaded, set_downloaded = use_state(False)
    text, set_text = use_state("")
    english, set_english = use_state("")
    busy, set_busy = use_state("")

    async def download():
        set_busy("Downloading the Hindi model (about 30 MB)...")
        try:
            await Translate.download_async("hi")
            set_downloaded(True)
            set_busy("")
        except RuntimeError as e:
            set_busy("Download failed: %s" % e)

    async def translate():
        set_english(await Translate.translate_async(text, "hi", "en"))

    if ready.loading:
        return Text("Getting ready...")
    if ready.error is not None:
        return Text("Translation needs the Android app.")
    if not (ready.value or downloaded):
        return View(
            Text(busy or "Translate Hindi offline: download the Hindi model once."),
            Pressable(Text("Download Hindi"), on_press=download),
            style={"flex": 1, "alignItems": "center", "justifyContent": "center", "gap": 16},
        )
    return View(
        TextInput(value=text, on_change_text=set_text, placeholder="हिंदी में लिखें"),
        Pressable(Text("Translate"), on_press=translate),
        Text(english),
        style={"flex": 1, "padding": 24, "gap": 16},
    )
```

## Languages

Languages are lowercase codes, the ones ML Kit uses: `"hi"` (Hindi), `"en"` (English), `"es"`, `"fr"`, `"de"`,
`"zh"`, `"ar"`, `"bn"`, `"mr"`, `"ta"`, `"te"`, `"gu"`, `"kn"`, `"ur"` and about 45 more.

```python
codes = await Translate.languages_async()     # ["af", "ar", "be", "bg", "bn", ..., "zh"]
```

Any pair works, for example `"es"` to `"hi"`; ML Kit translates through English inside the phone. A code ML Kit
does not know raises `RuntimeError("ML Kit cannot translate 'xx'")`, and a value that is not a 2 or 3 letter
lowercase code raises `ValueError` before anything native runs.

## Downloading models

```python
status = await Translate.status_async()            # {"supported": True, "downloaded": ["en", "hi"]}
have = await Translate.downloaded_async()          # ["en", "hi"]
ok = await Translate.is_ready_async("hi", "en")    # True when both are on the phone

await Translate.download_async("hi")                   # returns when the model is on the phone
await Translate.download_async("hi", wifi_only=True)   # waits for Wi-Fi first
await Translate.delete_async("hi")                     # frees the space
```

| Argument | Default | Description |
| --- | --- | --- |
| `language` | (required) | The language code to download, for example `"hi"`. `"en"` returns at once. |
| `wifi_only` | `False` | True waits until the phone is on Wi-Fi instead of using mobile data. The call does not return until then. |

- A model is about 30 MB. Ask the user before downloading, and say the size.
- `download_async` returns only when the model is on the phone, or raises `RuntimeError` when the download failed
  (no network, no space). There is no progress callback: show a spinner.
- A model stays on the phone until `delete_async` or until the app is uninstalled. It is shared by every translator
  in the app.
- `delete_async("en")` raises `RuntimeError`: English is built in.

## Translating

```python
english = await Translate.translate_async("आज मौसम बहुत अच्छा है", "hi")        # target defaults to "en"
hindi = await Translate.translate_async("The weather is lovely today", "en", "hi")
```

| Argument | Default | Description |
| --- | --- | --- |
| `text` | (required) | The text to translate, up to `MAX_TEXT` (10,000) characters. Several sentences are fine. |
| `source` | (required) | The language of `text`. |
| `target` | `"en"` | The language to translate into. |

- When `source == target`, or the text is blank, the text comes back unchanged and nothing native runs.
- When a language is not on the phone, `translate_async` raises `RuntimeError("not on the phone: hi
  (download_async first)")` at once. Check `is_ready_async` first.
- The first call for a pair takes about a second while the model loads; later calls take tens of milliseconds for a
  sentence. Call `close_async()` when you are done to free the memory (the models stay downloaded).
- ML Kit translates the text it is given and does not know which language it is. For mixed text such as Hinglish
  written in Latin letters, pass the language most of it is in, or clean it up first.

## Errors

| Error | When | What to do |
| --- | --- | --- |
| `ValueError` | A language is not a lowercase code, `text` is not a string, or it is longer than `MAX_TEXT`. | Fix the argument. Split long text into chunks. |
| `RuntimeError: not on the phone: hi (download_async first)` | `translate_async` with a language that is not downloaded. | Check `is_ready_async`, ask the user, call `download_async`. |
| `RuntimeError: the hi model did not download: ...` | No network, no space, or Google's server could not be reached. | Show the message and offer to try again later, on Wi-Fi. |
| `RuntimeError: ML Kit cannot translate 'xx'` | ML Kit does not know the code. | Use a code from `languages_async()`. |
| `RuntimeError: ML Kit did not answer in time` | A call took longer than its limit (60 seconds for a translation). | Try a shorter text; restart the app if it repeats. |
| `NotSupportedError` | iOS, the web or the desktop. | Check `status_async()["supported"]` and offer something else there. |
| `ModuleNotLinkedError` | The build does not include the module. | Add `"translate"` to `[tool.pyxpo] modules` and rebuild. |

## Web and desktop

There is no translator on iOS, the web or the desktop yet. `status_async()` returns
`{"supported": False, "downloaded": []}`, `close_async()` does nothing, and every other call raises
`NotSupportedError`, so the same app code runs everywhere and can hide the feature where it is missing.

## Recipe: a voice keyboard that types English

The [AI Keyboard](https://github.com/pyxpo/pyxpo) example app listens to Hindi with `pyxpo-speech`, translates it on
the phone and types the English into whatever app is open. This is the translation step, called with each finished
transcript:

```python
import pyxpo_translate as Translate


async def to_english(text: str, language: str) -> str:
    """English for what the user said. Asks for the model download instead of reaching the network silently."""
    if language == "en":
        return text
    if not await Translate.is_ready_async(language, "en"):
        raise LookupError(language)        # the keyboard shows "Download Hindi (30 MB)" and waits for a tap
    return await Translate.translate_async(text, language, "en")


async def on_download_tap(language: str) -> None:
    await Translate.download_async(language, wifi_only=True)
```

The keyboard has no screen of its own, so it shows the download offer in its panel and calls `download_async` only
after the tap.

## Production checklist

- Ask before downloading, say the size (about 30 MB per language), and prefer `wifi_only=True`.
- Check `is_ready_async` before translating, and handle `RuntimeError` from both download and translate.
- Call `close_async()` when the user leaves the translation feature, so the models do not stay in memory.
- Say in your privacy policy (and the Play data safety form) that text is translated on the device, and that the
  app downloads language models from Google. This package sends no text anywhere.
- Keep long text under `MAX_TEXT`; split by paragraph.
- Test on a real phone: the emulator works but is slower, and its first download can take a while.

## Testing

**On a phone or emulator**, run the quick start screen, tap Download Hindi (the emulator needs network), then
translate a sentence. Turn on airplane mode and translate again: it still works.

**Unit tests** run without a device. The module is a set of plain async functions, so swap in fakes with
`monkeypatch`:

```python
import asyncio

import pyxpo_translate as Translate

ON_PHONE = {"en"}


async def fake_ready(source, target="en"):
    return source in ON_PHONE and target in ON_PHONE


async def fake_download(language, wifi_only=False):
    ON_PHONE.add(language)


async def fake_translate(text, source, target="en"):
    if source not in ON_PHONE:
        raise RuntimeError("not on the phone: %s (download_async first)" % source)
    return "[%s>%s] %s" % (source, target, text)


def test_downloads_once_then_translates(monkeypatch):
    monkeypatch.setattr(Translate, "is_ready_async", fake_ready)
    monkeypatch.setattr(Translate, "download_async", fake_download)
    monkeypatch.setattr(Translate, "translate_async", fake_translate)

    async def run():
        if not await Translate.is_ready_async("hi"):
            await Translate.download_async("hi")
        return await Translate.translate_async("नमस्ते", "hi")

    assert asyncio.run(run()) == "[hi>en] नमस्ते"
```

## Troubleshooting

| Problem | Cause and fix |
| --- | --- |
| `download_async` never returns | `wifi_only=True` and the phone is on mobile data, or the network is down. Show a cancel option; try again on Wi-Fi. |
| `the hi model did not download` | No network, low storage, or Google's servers were not reachable (some networks block them). Try another network. |
| The first translation is slow | The model loads on the first call for a pair (about a second). Translate a short text when the feature opens to warm it up. |
| A Hinglish sentence comes back half translated | ML Kit expects one language. Latin-letter Hindi words are often left as they are. Pass Devanagari text, or clean it up first (for example with a language model). |
| Names or brand words are translated | ML Kit translates every word it knows. Put such words back yourself, or keep them out of the text. |
| `NotSupportedError` on iOS or in the browser | There is no translator there yet. Check `status_async()["supported"]`. |
| `ModuleNotLinkedError` | The build does not include the module. Add it to `[tool.pyxpo] modules` and rebuild. |
| The Android build hangs downloading ML Kit | Gradle cannot reach `dl.google.com`. Check the network; if IPv4 to Google is blocked, `JAVA_TOOL_OPTIONS=-Djava.net.preferIPv6Addresses=true` can help. |
| `RuntimeWarning: coroutine ... was never awaited` | The check was started with `use_effect(lambda: coro())`. Use `use_async(lambda: Translate.is_ready_async("hi"), [])`. |

## FAQ

**Does my text leave the phone?**
No. Translation runs on the device and the package never sends text anywhere or logs it. The network is used only by
`download_async`, to fetch model files.

**Why does the app need the INTERNET permission?**
For `download_async`. If your app never downloads models, it still has the permission (it comes with the module),
but nothing is sent.

**How good is the translation?**
ML Kit's models are small and run on the phone, so they are good for everyday sentences and weaker than large cloud
models for idioms and long, formal text. To polish the result (tone, grammar), run the English through an on-device
language model afterwards.

**Can I ship the model inside the app?**
Not with ML Kit: its translation models are always downloaded at run time.

**Will iOS be supported?**
Not in this release. Apple's on-device Translation framework is the likely route.

## API reference

**Functions**

| Name | Description |
| --- | --- |
| `status_async() -> dict` | `{"supported": bool, "downloaded": [codes]}`. Never raises on other platforms. |
| `languages_async() -> list` | Every language code ML Kit can translate. |
| `downloaded_async() -> list` | The codes whose models are on the phone; always includes `"en"`. |
| `is_ready_async(source, target="en") -> bool` | True when both languages are on the phone. |
| `download_async(language, wifi_only=False) -> None` | Downloads one language's model; returns when it is on the phone. |
| `delete_async(language) -> None` | Removes a downloaded model. English cannot be removed. |
| `translate_async(text, source, target="en") -> str` | Translates on the phone; raises when a language is not downloaded. |
| `close_async() -> None` | Frees the open translators. Does nothing on other platforms. |
| `statusAsync`, `languagesAsync`, `downloadedAsync`, `isReadyAsync`, `downloadAsync`, `deleteAsync`, `translateAsync`, `closeAsync` | Expo-style names for the functions above. |

**Constants and types**

| Name | Description |
| --- | --- |
| `MAX_TEXT` | The longest text one `translate_async` call takes: 10,000 characters. |
| `NotSupportedError` | Raised where there is no translator (re-exported from `pyxpo.module_api`). |

## License

MIT. ML Kit is a Google product; this package is not made or endorsed by Google, and using ML Kit means agreeing to
Google's ML Kit terms.
