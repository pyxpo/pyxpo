"""Offline text translation for pyxpo apps (Android): Google ML Kit's on-device translation models.

    import pyxpo_translate as Translate

    if not await Translate.is_ready_async("hi", "en"):
        await Translate.download_async("hi")          # about 30 MB, once; ask the user first
    english = await Translate.translate_async("मैं कल आऊँगा", "hi", "en")

A language model downloads only when `download_async` asks for it. After that every translation runs on the
phone: the text is never sent anywhere, and `translate_async` refuses a language that is not downloaded instead
of fetching it. English is built in. Language codes are BCP-47 tags ML Kit knows: "hi", "en", "es", "zh", ...
iOS, the web and the desktop raise `NotSupportedError` (`status_async` reports `supported: False`).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from pyxpo.module_api import NotSupportedError, call, platform, require_linked

__version__ = "0.1.0a1"

#: The longest text one `translate_async` call takes (characters).
MAX_TEXT = 10000

_LANG = re.compile(r"^[a-z]{2,3}$")


def _native() -> bool:
    if platform() != "android":
        return False
    require_linked("Translate", "translate", package="pyxpo-translate")
    return True


def _need_native(what: str) -> None:
    if not _native():
        raise NotSupportedError("%s needs Android: pyxpo-translate does not support %s yet" % (what, platform()))


def _lang(code: Any) -> str:
    if not (isinstance(code, str) and _LANG.match(code)):
        raise ValueError("a language is a lowercase code such as 'hi' or 'en', not %r" % (code,))
    return code


async def status_async() -> Dict[str, Any]:
    """`supported` (this platform translates) and `downloaded` (the language codes on the phone)."""
    if not _native():
        return {"supported": False, "downloaded": []}
    return {"supported": True, "downloaded": await downloaded_async()}


async def languages_async() -> List[str]:
    """Every language code ML Kit can translate (about 60)."""
    _need_native("languages_async")
    return list(await call("Translate", "languages", reply=True))


async def downloaded_async() -> List[str]:
    """The language codes whose models are on the phone. Always includes "en"."""
    _need_native("downloaded_async")
    return list(await call("Translate", "downloaded", reply=True))


async def is_ready_async(source: str, target: str = "en") -> bool:
    """True when both languages are on the phone, so `translate_async(text, source, target)` works offline."""
    source, target = _lang(source), _lang(target)
    have = set(await downloaded_async())
    return source in have and target in have


async def download_async(language: str, wifi_only: bool = False) -> None:
    """Downloads one language's model (about 30 MB) from Google, once; returns when it is on the phone.
    `wifi_only=True` waits for Wi-Fi instead of using mobile data. Ask the user before calling it."""
    _lang(language)
    _need_native("download_async")
    await call("Translate", "download", language, {"wifiOnly": bool(wifi_only)}, reply=True)


async def delete_async(language: str) -> None:
    """Removes a downloaded language model to free space. English is built in and cannot be removed."""
    _lang(language)
    _need_native("delete_async")
    await call("Translate", "delete", language, reply=True)


async def translate_async(text: str, source: str, target: str = "en") -> str:
    """Translates `text` from `source` to `target` on the phone. Raises `RuntimeError` when a language is not
    downloaded (see `is_ready_async`). The same language, or blank text, comes back unchanged."""
    if not isinstance(text, str):
        raise ValueError("translate_async needs text, not %r" % (text,))
    if len(text) > MAX_TEXT:
        raise ValueError("translate_async takes up to %d characters at a time" % MAX_TEXT)
    source, target = _lang(source), _lang(target)
    _need_native("translate_async")
    if source == target or not text.strip():
        return text
    return str(await call("Translate", "translate", text, source, target, reply=True))


async def close_async() -> None:
    """Frees the open translators (their models stay downloaded). The next translation opens one again."""
    if _native():
        await call("Translate", "close", reply=True)


# Expo-style names
statusAsync = status_async
languagesAsync = languages_async
downloadedAsync = downloaded_async
isReadyAsync = is_ready_async
downloadAsync = download_async
deleteAsync = delete_async
translateAsync = translate_async
closeAsync = close_async
