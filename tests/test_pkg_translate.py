"""pyxpo-translate: the calls, argument checks, other-platform behaviour and the Android native wiring."""
import asyncio
import json
import re
from pathlib import Path

import pytest

from pyxpo.build import autolink
from pyxpo.module_api import ModuleNotLinkedError, NotSupportedError
from pyxpo.module_testing import FakeBridge

import pyxpo_translate as Translate

PKG = Path(Translate.__file__).parent
MAIN = PKG / "android" / "src" / "main"
KT = MAIN / "java" / "dev" / "pyxpo" / "modules" / "translate" / "TranslateModule.kt"


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("os_name", ["desktop", "web", "ios"])
def test_other_platforms(os_name):
    with FakeBridge(os_name) as fb:
        assert run(Translate.status_async()) == {"supported": False, "downloaded": []}
        run(Translate.close_async())
        for coro in (Translate.languages_async(), Translate.downloaded_async(), Translate.is_ready_async("hi"),
                     Translate.download_async("hi"), Translate.delete_async("hi"),
                     Translate.translate_async("नमस्ते", "hi")):
            with pytest.raises(NotSupportedError):
                run(coro)
        assert fb.calls == []


@pytest.fixture
def phone():
    with FakeBridge("android", modules=("Translate",)) as fb:
        have = ["en"]
        fb.on("Translate", "downloaded", lambda: list(have))
        fb.on("Translate", "languages", lambda: ["en", "hi"])
        fb.on("Translate", "download", lambda lang, o: have.append(lang))
        fb.on("Translate", "delete", lambda lang: have.remove(lang))
        fb.on("Translate", "translate", lambda text, s, t: "I will come tomorrow")
        fb.on("Translate", "close", lambda: None)
        yield fb


def test_download_then_translate(phone):
    assert run(Translate.status_async()) == {"supported": True, "downloaded": ["en"]}
    assert run(Translate.is_ready_async("hi", "en")) is False
    run(Translate.download_async("hi"))
    assert ("Translate", "download", ("hi", {"wifiOnly": False})) in phone.calls
    assert run(Translate.is_ready_async("hi")) is True
    assert run(Translate.translate_async("मैं कल आऊँगा", "hi", "en")) == "I will come tomorrow"
    assert phone.calls[-1] == ("Translate", "translate", ("मैं कल आऊँगा", "hi", "en"))
    assert run(Translate.languages_async()) == ["en", "hi"]
    run(Translate.delete_async("hi"))
    assert run(Translate.downloaded_async()) == ["en"]
    run(Translate.close_async())


def test_wifi_only(phone):
    run(Translate.download_async("es", wifi_only=True))
    assert phone.calls[-1] == ("Translate", "download", ("es", {"wifiOnly": True}))


def test_same_language_or_blank_skips_native(phone):
    assert run(Translate.translate_async("hello", "en", "en")) == "hello"
    assert run(Translate.translate_async("  ", "hi")) == "  "
    assert not any(c[1] == "translate" for c in phone.calls)


@pytest.mark.parametrize("bad", ["HI", "hindi", "", None, "h"])
def test_bad_language(phone, bad):
    with pytest.raises(ValueError):
        run(Translate.translate_async("x", bad))
    with pytest.raises(ValueError):
        run(Translate.download_async(bad))
    assert phone.calls == []


def test_bad_text(phone):
    with pytest.raises(ValueError):
        run(Translate.translate_async(None, "hi"))
    with pytest.raises(ValueError):
        run(Translate.translate_async("x" * (Translate.MAX_TEXT + 1), "hi"))


def test_native_error_is_runtime_error():
    with FakeBridge("android", modules=("Translate",)) as fb:
        def fail(text, s, t):
            raise RuntimeError("not on the phone: hi (download_async first)")
        fb.on("Translate", "translate", fail)
        with pytest.raises(RuntimeError, match="download_async"):
            run(Translate.translate_async("नमस्ते", "hi"))


def test_not_linked():
    with FakeBridge("android"):
        with pytest.raises(ModuleNotLinkedError, match="pyxpo-translate"):
            run(Translate.status_async())


def test_aliases():
    assert Translate.translateAsync is Translate.translate_async
    assert Translate.isReadyAsync is Translate.is_ready_async
    assert Translate.downloadAsync is Translate.download_async


def test_native_wiring():
    meta = json.loads((PKG / "pyxpo-module.json").read_text())
    assert meta["name"] == "translate" and meta["native"] == "Translate" and meta["name"] in autolink.OFFICIAL
    assert meta["nativeContract"] == 4    # ctx.context: the keyboard calls it headless
    assert any(d.startswith("com.google.mlkit:translate:") for d in meta["android"]["dependencies"])
    src = KT.read_text()
    calls = set(re.findall(r'"(\w+)" ->', src))
    assert {"languages", "downloaded", "download", "delete", "translate", "close"} <= calls
    # translating never downloads: a missing model is an error, not a fetch
    assert "download_async first" in src and "downloadModelIfNeeded" not in src
    assert "Log." not in src     # text is never logged
    assert "INTERNET" in (MAIN / "AndroidManifest.xml").read_text()
