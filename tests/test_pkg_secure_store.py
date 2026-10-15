"""pyxpo-secure-store: expo-secure-store API, option checks, desktop memory store and the native calls."""
import asyncio

import pytest

from pyxpo.module_testing import FakeBridge

import pyxpo_secure_store as SecureStore


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def clean():
    SecureStore._memory.clear()


def test_desktop_round_trip():
    assert run(SecureStore.getItemAsync("token")) is None
    run(SecureStore.setItemAsync("token", "abc"))
    run(SecureStore.set_item_async("token", "other", {"keychainService": "work"}))
    assert run(SecureStore.get_item_async("token")) == "abc"
    assert run(SecureStore.get_item_async("token", {"keychainService": "work"})) == "other"
    run(SecureStore.deleteItemAsync("token"))
    run(SecureStore.delete_item_async("token"))
    assert run(SecureStore.get_item_async("token")) is None
    assert run(SecureStore.isAvailableAsync()) is False
    assert run(SecureStore.canUseBiometricAuthenticationAsync()) is False


def test_validation():
    for bad in ("", "a b", "x/y", "ü", None, 5):
        with pytest.raises(ValueError):
            run(SecureStore.get_item_async(bad))
    with pytest.raises(TypeError, match="json.dumps"):
        run(SecureStore.set_item_async("k", {"a": 1}))
    with pytest.raises(ValueError, match="unknown"):
        run(SecureStore.set_item_async("k", "v", {"require_authentication": True}))
    with pytest.raises(ValueError):
        run(SecureStore.set_item_async("k", "v", {"keychainAccessible": 9}))
    with pytest.raises(ValueError):
        run(SecureStore.set_item_async("k", "v", {"keychainService": "a:b"}))


def test_native_calls():
    store = {}
    with FakeBridge("ios") as fb:
        fb.on("SecureStore", "set", lambda k, v, o: store.__setitem__(o["keychainService"] + k, v))
        fb.on("SecureStore", "get", lambda k, o: store.get(o["keychainService"] + k))
        fb.on("SecureStore", "delete", lambda k, o: store.pop(o["keychainService"] + k, None))
        fb.on("SecureStore", "canUseBiometric", lambda: True)
        run(SecureStore.set_item_async("k.1", "v", {"requireAuthentication": True, "authenticationPrompt": "Unlock",
                                                    "keychainAccessible": SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY}))
        assert fb.calls[0][2] == ("k.1", "v", {"keychainService": "app", "requireAuthentication": True,
                                              "authenticationPrompt": "Unlock", "keychainAccessible": 6, "accessGroup": ""})
        assert run(SecureStore.get_item_async("k.1")) == "v"
        run(SecureStore.delete_item_async("k.1"))
        assert run(SecureStore.get_item_async("k.1")) is None
        assert run(SecureStore.can_use_biometric_authentication_async()) is True
        assert run(SecureStore.is_available_async()) is True
    assert SecureStore._memory == {}
