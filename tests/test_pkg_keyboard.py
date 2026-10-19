"""pyxpo-keyboard: the app calls, option checks, desktop defaults and the Android input-method wiring."""
import asyncio
import json
from pathlib import Path

import pytest

from pyxpo.module_api import ModuleNotLinkedError, NotSupportedError
from pyxpo.module_testing import FakeBridge

import pyxpo_keyboard as Keyboard

PKG = Path(Keyboard.__file__).parent


def run(coro):
    return asyncio.run(coro)


def test_desktop_defaults():
    assert run(Keyboard.statusAsync()) == {"supported": False, "enabled": False, "selected": False, "id": ""}
    assert run(Keyboard.get_options_async()) == Keyboard.OPTIONS
    assert run(Keyboard.set_options_async(number_row=True))["number_row"] is True
    run(Keyboard.open_settings_async())
    run(Keyboard.show_picker_async())


def test_web_defaults():
    # the web page links no Keyboard module: the calls answer like the desktop instead of ModuleNotLinkedError
    with FakeBridge("web") as fb:
        assert run(Keyboard.status_async())["supported"] is False
        assert run(Keyboard.get_options_async()) == Keyboard.OPTIONS
        assert run(Keyboard.set_options_async(sound=True))["sound"] is True
        run(Keyboard.open_settings_async())
        run(Keyboard.show_picker_async())
        assert fb.calls == []


def test_bad_options():
    with pytest.raises(ValueError, match="unknown or non-boolean"):
        run(Keyboard.set_options_async(rainbow=True))
    with pytest.raises(ValueError, match="unknown or non-boolean"):
        run(Keyboard.set_options_async(haptics="yes"))


def test_android_calls():
    status = {"supported": True, "enabled": True, "selected": False, "id": "app/dev.pyxpo.modules.keyboard.KeyboardService"}
    with FakeBridge("android") as fb:
        fb.on("Keyboard", "status", lambda: status)
        fb.on("Keyboard", "openSettings", lambda: None)
        fb.on("Keyboard", "showPicker", lambda: None)
        fb.on("Keyboard", "getOptions", lambda: dict(Keyboard.OPTIONS))
        fb.on("Keyboard", "setOptions", lambda o: {**Keyboard.OPTIONS, **o})
        assert run(Keyboard.status_async()) == status
        run(Keyboard.open_settings_async())
        run(Keyboard.show_picker_async())
        assert run(Keyboard.get_options_async()) == Keyboard.OPTIONS
        assert run(Keyboard.set_options_async(sound=True))["sound"] is True
        assert [c[1] for c in fb.calls] == ["status", "openSettings", "showPicker", "getOptions", "setOptions"]
        assert fb.calls[-1][2] == ({"sound": True},)


def test_ios_has_no_keyboard_yet():
    with FakeBridge("ios") as fb:
        fb.on("Keyboard", "status", lambda: {"supported": False, "enabled": False, "selected": False, "id": ""})
        assert run(Keyboard.status_async())["supported"] is False
        with pytest.raises(NotSupportedError):
            run(Keyboard.show_picker_async())
        with pytest.raises(NotSupportedError):
            run(Keyboard.set_options_async(haptics=False))


def test_not_linked():
    with FakeBridge("android"):
        with pytest.raises(ModuleNotLinkedError):
            run(Keyboard.status_async())


def test_android_input_method_is_declared():
    meta = json.loads((PKG / "pyxpo-module.json").read_text())
    assert meta["native"] == "Keyboard" and meta["android"]["classes"] == ["dev.pyxpo.modules.keyboard.KeyboardModule"]
    main = PKG / "android" / "src" / "main"
    manifest = (main / "AndroidManifest.xml").read_text()
    for part in ('android:name="dev.pyxpo.modules.keyboard.KeyboardService"', "android.permission.BIND_INPUT_METHOD",
                 '"android.view.InputMethod"', '"android.view.im"', "@xml/px_keyboard_method", 'android:exported="true"'):
        assert part in manifest
    assert (main / "res" / "xml" / "px_keyboard_method.xml").is_file()


def test_android_keeps_private_fields_private():
    # passwords, numeric PINs and incognito fields must be marked sensitive (no AI, no voice later)
    kt = (PKG / "android" / "src" / "main" / "java" / "dev" / "pyxpo" / "modules" / "keyboard" / "KeyboardService.kt").read_text()
    for part in ("TYPE_TEXT_VARIATION_PASSWORD", "TYPE_TEXT_VARIATION_VISIBLE_PASSWORD", "TYPE_TEXT_VARIATION_WEB_PASSWORD",
                 "TYPE_NUMBER_VARIATION_PASSWORD", "IME_FLAG_NO_PERSONALIZED_LEARNING"):
        assert part in kt


def test_official_module():
    from pyxpo.build.autolink import OFFICIAL
    assert "keyboard" in OFFICIAL


def test_android_survives_a_theme_switch():
    # the system's reset on a light/dark switch left the keys invisible (surface alpha 0): the IME handles uiMode
    main = PKG / "android" / "src" / "main"
    assert 'android:configChanges="uiMode"' in (main / "res" / "xml" / "px_keyboard_method.xml").read_text()
    kt = (main / "java" / "dev" / "pyxpo" / "modules" / "keyboard" / "KeyboardService.kt").read_text()
    assert "override fun onConfigurationChanged" in kt and "setInputView(onCreateInputView())" in kt
    # a rebuilt view starts above the navigation bar, as no insets reach it again
    assert "root.setPadding(0, 0, 0, navInset)" in kt


def test_android_toolbar_status_and_field():
    field = {"kind": "text", "action": "Send", "private": False, "multiline": False, "app": "com.example.chat"}
    with FakeBridge("android", modules=("Keyboard",)) as fb:
        fb.on("Keyboard", "setToolbar", lambda b: None)
        fb.on("Keyboard", "setStatus", lambda t: None)
        fb.on("Keyboard", "field", lambda: field)
        fb.on("Keyboard", "commitText", lambda t: None)
        fb.on("Keyboard", "getText", lambda o: {"before": "Hi ", "selected": "", "after": ""})
        run(Keyboard.set_toolbar_async([{"id": "mic", "label": "🎤", "description": "Voice typing"}]))
        run(Keyboard.setStatusAsync("Listening…"))
        assert run(Keyboard.get_field_async()) == field
        run(Keyboard.commit_text_async("hello "))
        assert run(Keyboard.get_text_async(before=20, after=0))["before"] == "Hi "
        args = {c[1]: c[2] for c in fb.calls}
        assert args["setToolbar"] == ([{"id": "mic", "label": "🎤", "description": "Voice typing", "active": False}],)
        assert args["setStatus"] == ("Listening…",)
        assert args["commitText"] == ("hello ",)
        assert args["getText"] == ({"before": 20, "after": 0},)


@pytest.mark.parametrize("buttons", [[{"id": "", "label": "x"}], [{"id": "a"}], ["mic"], [{"id": "a", "label": "x", "color": 1}],
                                     [{"id": "a", "label": "x"}, {"id": "a", "label": "y"}],
                                     [{"id": str(i), "label": "x"} for i in range(7)]])
def test_bad_toolbar(buttons):
    with FakeBridge("android", modules=("Keyboard",)) as fb:
        with pytest.raises(ValueError):
            run(Keyboard.set_toolbar_async(buttons))
        assert fb.calls == []


def test_toolbar_elsewhere():
    # the desktop has no keyboard: the toolbar and status calls do nothing, typing into a field cannot happen
    run(Keyboard.set_toolbar_async([{"id": "mic", "label": "🎤"}]))
    run(Keyboard.set_status_async("hi"))
    assert run(Keyboard.get_field_async()) is None
    with pytest.raises(NotSupportedError):
        run(Keyboard.commit_text_async("x"))
    with pytest.raises(NotSupportedError):
        run(Keyboard.get_text_async())
    with pytest.raises(ValueError):
        run(Keyboard.get_text_async(before=-1))
    with FakeBridge("ios") as fb:
        with pytest.raises(NotSupportedError):
            run(Keyboard.set_toolbar_async([]))
        assert fb.calls == []


def test_toolbar_and_input_listeners():
    from pyxpo import modules
    seen = []
    offs = [Keyboard.add_toolbar_listener(seen.append), Keyboard.addInputListener(seen.append)]
    modules.dispatch({"name": "Keyboard.toolbar", "data": {"id": "mic", "field": {"kind": "text"}}})
    modules.dispatch({"name": "Keyboard.input", "data": {"state": "finish"}})
    for off in offs:
        off()
    modules.dispatch({"name": "Keyboard.toolbar", "data": {"id": "mic"}})
    assert seen == [{"id": "mic", "field": {"kind": "text"}}, {"state": "finish"}]


def test_android_toolbar_never_sends_field_text():
    # a tap tells Python which button and what kind of field, never what is typed; private fields refuse
    kt = (PKG / "android" / "src" / "main" / "java" / "dev" / "pyxpo" / "modules" / "keyboard" / "KeyboardService.kt").read_text()
    assert 'PxProcess.emit(TOOLBAR, mapOf("id" to id, "field" to fieldKind(f)))' in kt
    assert kt.count("if (f.sensitive) return") >= 3
    meta = json.loads((PKG / "pyxpo-module.json").read_text())
    assert meta["nativeContract"] == 4   # PxProcess / ctx.context (headless calls)
